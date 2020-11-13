"""This module contains the main denoise function"""

import os
import sys
import argparse
import time as tm

import torch
import torch.distributed as dist
from torch.utils.data.distributed import DistributedSampler 
from torch.utils.data import DataLoader
from torch.nn.parallel import DistributedDataParallel

from run_hopt import load_yaml

from distributed import set_random_seed

from dataloader import CropLoader
from dataloader import PlaneLoader
from model import  *
from args import Args

from model_utils import print_summary_file
from model_utils import weight_scan

import train

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.utils import get_freer_gpu


def main(args):
    """This is the main function"""

    n = torch.cuda.device_count() // args.local_world_size
    args.dev_ids = list(range(args.local_rank * n, (args.local_rank + 1) * n))

    #load datasets
    set_random_seed(0)
    train_data = CropLoader(args,'train','collection')
    train_sampler = DistributedSampler(dataset=train_data)
    train_loader = DataLoader(dataset=train_data, sampler=train_sampler,
                              shuffle=True, batch_size=args.batch_size,
                              num_workers=args.num_workers)
    val_data = PlaneLoader(args,'val','collection')

    model = eval('get_' + args.model)(args)

    #train
    return train.train(args, train_loader, val_data,
                model)


def spmd_main(args):
    """ Spawn distributed processes """
    dist.init_process_group(backend="nccl")

    main(args)

    dist.destroy_process_group()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--card", type=str, help='yaml config file path',
                        default="./denoising/configcards/default_config.yaml")
    parser.add_argument("--local_rank", default=0, type=int,
                    help="Distributed utility")
    parser.add_argument("--local_world_size", default=1, type=int,
                    help="Distributed utility")

    # load configuration
    args = parser.parse_args()
    parameters = load_yaml(args["card"])
    parameters["local_rank"] = args.local_rank
    parameters["local_world_size"] = args.local_world_size
    parameters["rank"] = dist.get_rank()
    args = Args(**parameters)
    if args.rank == 0:
        args.build_directories()
        print_summary_file(args)

    # main
    START = tm.time()
    spmd_main(args)
    print(f'[{os.getpid()}] Program done in {tm.time()-START}')