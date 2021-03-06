from collections import Counter
import torch.nn as nn
from Solver.OptimizerBuilder import *
from fvcore.common.config import CfgNode

class Solver(nn.Module):

    def __init__(self, model:nn.Module, configs:CfgNode):
        """
        Args:
            optimizer (torch.optim.Optimizer):
        """
        self._optimizer = build_optimizer(configs, model)
        self._scheduler = build_lr_scheduler(configs, self._optimizer)
        # NOTE: some heuristics on what LR to summarize
        # summarize the param group with most parameters
        largest_group = max(len(g["params"]) for g in self._optimizer.param_groups)

        if largest_group == 1:
            # If all groups have one parameter,
            # then find the most common initial LR, and use it for summary
            lr_count = Counter([g["lr"] for g in self._optimizer.param_groups])
            lr = lr_count.most_common()[0][0]
            for i, g in enumerate(self._optimizer.param_groups):
                if g["lr"] == lr:
                    self._best_param_group_id = i
                    break
        else:
            for i, g in enumerate(self._optimizer.param_groups):
                if len(g["params"]) == largest_group:
                    self._best_param_group_id = i
                    break
        pass
    @property
    def solver_name(self):
        return type(self._optimizer).__name__ + '_' + type(self._scheduler).__name__

    @property
    def optimizer(self):
        return self._optimizer

    @property
    def scheduler(self):
        return self._scheduler
    
    @property
    def learnrate(self):
        return self._optimizer.param_groups[self._best_param_group_id]["lr"]

    def load_state_dict(self, state_dict:dict):
        self._best_param_group_id = state_dict.pop('best_param_group_id') \
            if 'best_param_group_id' in state_dict else self._best_param_group_id
        if 'optimizer' in state_dict:
            cp = state_dict.pop("optimizer")
            self.optimizer.load_state_dict(cp)
        if "scheduler" in state_dict:
            cp = state_dict.pop("scheduler")
            cp = {'{}'.format(k): cp[k] for k in cp if k in ['last_epoch']}
            self.scheduler.load_state_dict(cp)
            self.optimizer.step()
            self.scheduler.step()
        # if 'optimizer' in state_dict:
        #     state = state_dict['optimizer']
        #     self._optimizer.load_state_dict(state)
        #     for k, v in self._optimizer.state.items():  # key is Parameter, val is a dict {key='momentum_buffer':tensor(...)}
        #         if 'momentum_buffer' not in v:
        #             continue
        #         self._optimizer.state[k]['momentum_buffer'] = self._optimizer.state[k]['momentum_buffer'].to(device)
        # if 'scheduler' in state_dict:
        #     state = state_dict['scheduler']
        #     self._scheduler.last_epoch = state['last_epoch']
        #     self._optimizer.step()
        #     self._scheduler.step()

    def state_dict(self):
        state = {
            'best_param_group_id':self._best_param_group_id,
            'optimizer': self._optimizer.state_dict(),
            'scheduler': {
                'last_epoch': self._scheduler.last_epoch
            }
        }
        return state
    
    def step(self, losses_dict):
        lr = self._optimizer.param_groups[self._best_param_group_id]["lr"]
        self._optimizer.zero_grad()
        if isinstance(losses_dict, dict):
            losses = sum(loss.mean() for loss in losses_dict.values())
        elif torch.is_tensor(losses_dict):
            losses = losses_dict.mean()
        else:
            raise Exception("Loss go wrong.")
        losses.backward()
        self._optimizer.step()
        self._scheduler.step()
        return losses
