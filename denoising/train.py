import sys
import os
from math import ceil
from math import isnan
import numpy as np

import torch
import torch.distributed as dist
from torch import optim
from torch import nn
from torch.utils.data.distributed import DistributedSampler 
from torch.utils.data import DataLoader

from model_utils import freeze_weights
from model_utils import MyDDP

from losses import get_loss

from time import time as tm


def time_windows(plane, w, stride):
    """ This function takes a plane and takes time windows """
    B, C, H, W = plane.size()
    n = ceil((W-w)/stride) + 1
    base = np.arange(n).reshape([-1,1]) * stride
    idxs = [[0, w]] + base
    windows = []
    div = torch.zeros_like(plane)
    for start, end in idxs:
        windows.append(plane[:,:,:,start:end])
        div[:,:,:,start:end] += 1        
    return div, windows, idxs


def train_epoch(args, epoch, train_loader, model, optimizer,
                balance_ratio, task):
    if args.rank == 0:
        print('\n[+] Training')
    start = tm()
    loss_fn = get_loss(args.loss_fn)(args.a) if task=='dn' else \
              get_loss("bce")(balance_ratio)
    model.train()
    for noisy, clear in train_loader:
        _, cwindows, _ = time_windows(clear, args.patch_w, args.patch_stride)
        _, nwindows, _ = time_windows(noisy, args.patch_w, args.patch_stride)
        for nwindow, cwindow in zip(nwindows, cwindows):
            cwindow = cwindow.to(args.dev_ids[0])
            nwindow = nwindow.to(args.dev_ids[0])
            optimizer.zero_grad()
            out, loss0 = model(nwindow)
            loss = loss_fn(out, cwindow) + loss0
            loss.backward()
            optimizer.step()
    return np.array([loss.item()]), tm() - start


def inference(test_loader, w, stride, model, dev):
    model.eval()
    outs = []
    for noisy, _ in test_loader:
        div, nwindows, idxs = time_windows(noisy, w, stride)
        out = torch.zeros_like(noisy)
        for nwindow, (start, end) in zip(nwindows, idxs):
            nwindow = nwindow.to(dev)
            out[:,:,:,start:end] += model(nwindow).data
        outs.append( out/div )
    return torch.cat(outs)


def compute_val_loss(test_loader, outputs, args, task):
    loss = []
    ssim = []
    mse = []
    psnr = []
    loss_fn = get_loss(args.loss_fn)(args.a) if task=='dn' else get_loss("bce")(0.5)
    if task == 'dn':
        ssim_fn = get_loss('ssim')()
        mse_fn = get_loss('mse')()
        psnr_fn = get_loss('psnr')
    for (_, target), output in zip(test_loader, outputs):
        # works only with unit batch_size
        output = output.unsqueeze(0).to(args.dev_ids[0])
        target = target.to(args.dev_ids[0])
        loss.append( loss_fn(output, target).cpu().item() )
        if task == 'dn':
            ssim.append( 1-ssim_fn(target, output).cpu().item() )
            mse.append( mse_fn(output, target).cpu().item() )
            psnr.append( psnr_fn(target.cpu(), output.cpu()).item() )
    if args.rank==0:
        fname = os.path.join(args.dir_testing, "labels")
        torch.save(target.cpu(), fname)
        fname = os.path.join(args.dir_testing, "results")
        torch.save(output.cpu(), fname)

    n = len(loss)
    if task == 'dn':
        return np.array([np.mean(loss), np.std(loss)/np.sqrt(n),
                np.mean(ssim), np.std(ssim)/np.sqrt(n),
                np.mean(psnr), np.std(psnr)/np.sqrt(n),
                np.mean(mse), np.std(mse)/np.sqrt(n)])
    return np.array([np.mean(loss), np.std(loss)/np.sqrt(n)])


def test_epoch(test_data, model, args, task, dry_inference=True):
    """
    Parameters:
        test_data: torch.utils.data.DataLoader, based on PlaneLoader
        task: str, either roi or dn
    Outputs:
        np.array: n metrics, shape (2*n)
        torch.Tensor: denoised data, shape (batch,C,W,H)
        float: dry inference time
    """
    test_sampler = DistributedSampler(dataset=test_data, shuffle=False)
    test_loader = DataLoader(dataset=test_data, sampler=test_sampler,
                              batch_size=1,
                              num_workers=args.num_workers)
    if args.rank == 0:
        print('\n[+] Testing')
    start = tm()
    outputs = inference(test_loader, args.patch_w, args.patch_stride, model,
                     args.dev_ids[0])
    if task == 'dn':
        mask = (outputs <= args.threshold) & (outputs >= -args.threshold)
        outputs[mask] = 0
    dry_time = tm() - start

    if dry_inference:
        return outputs, dry_time
    return compute_val_loss(test_loader, outputs, args, task), outputs, dry_time
    


########### main train function
def train(args, train_data, val_data, model):
    task = args.task
    channel = args.channel
    # check if load existing model
    model = MyDDP(model.to(args.dev_ids[0]), device_ids=args.dev_ids,
                   find_unused_parameters=True)

    if args.load:
        if args.load_path is None:
            #resume a previous training from an epoch
            #time train
            fname = os.path.join(args.dir_timings, 'timings_train.npy')
            time_train = list(np.load(fname))

            #time test
            fname = os.path.join(args.dir_timings, 'timings_test.npy')
            time_test = list(np.load(fname))

            #loss_sum
            fname = os.path.join(args.dir_metrics, 'loss_sum.npy')
            loss_sum = list(np.load(fname).T)
    
            #test_epochs
            fname = os.path.join(args.dir_metrics, 'test_epochs.npy')
            test_epochs = list(np.load(fname))

            #test metrics
            fname = os.path.join(args.dir_metrics, 'test_metrics.npy')
            test_metrics = list(np.load(fname).T)

            fname = os.path.join(args.dir_saved_models,
                                 f'{args.model}_{task}_{args.load_epoch}.dat')
            epoch = args.load_epoch + 1
       
        else:
            #load a trained model
            fname = args.load_path
            epoch = 1
            loss_sum = []
            test_metrics = []
            test_epochs = []
            time_train = []
            time_test = []

        if args.rank == 0:
            print(f'Loading model at {fname}')
        map_location = {"cuda:{0:d}": f"cuda:{args.local_rank:d}"}
        model.load_state_dict(torch.load(fname, map_location=map_location))
    else:
        epoch = 1
        loss_sum = []
        test_metrics = []
        test_epochs = []
        time_train = []
        time_test = []

    best_loss = 1e10
    best_loss_std = 0
    best_model_name = os.path.join(args.dir_saved_models,f"{args.model}_-1.dat")
        
    # initialize optimizer
    #optimizer = optim.Adam(list(model.parameters()), lr=args.lr,
    #                       amsgrad=args.amsgrad)
    optimizer = optim.SGD(list(model.parameters()), lr=args.lr,
                           momentum=0.8)
    optimizer = optim.Adam(list(model.parameters()), amsgrad=True)

    train_sampler = DistributedSampler(dataset=train_data, shuffle=True)
    train_loader = DataLoader(dataset=train_data, sampler=train_sampler,
                              batch_size=1,
                              num_workers=args.num_workers)

    # main training loop
    while epoch <= args.epochs:

        # train
        start = tm()
        train_sampler.set_epoch(epoch)
        balance_ratio = train_data.balance_ratio if task=='roi' else None 
        loss, t = train_epoch(args, epoch, train_loader, model,
                              optimizer, balance_ratio,
                              task=task)
        end = tm() - start
        loss_sum.append(loss)
        time_train.append(t)
        if epoch % args.epoch_log == 0 and (not args.scan) and args.rank==0:
            print(f"Epoch: {epoch:3}, Loss: {loss_sum[-1][0]:6.5}, epoch time: {end:.4}s")

        # test
        if epoch % args.epoch_test == 0 and epoch>=args.epoch_test_start:
            test_epochs.append(epoch)
            start = tm()
            x, _, t = test_epoch(val_data, model, args, task,
                              dry_inference=False)
            end = tm() - start
            test_metrics.append(x)
            time_test.append(t)
            if args.rank == 0:
                if args.task == 'roi':
                    print(f"Test loss on {channel:10} APAs: {x[0]:.5} +- {x[1]:.5}")
                if args.task == 'dn':
                    print(f"Test on {channel:10} APAs: {'loss:':7} {x[0]:.5} +- {x[1]:.5}\n\
                         {'ssim:':7} {x[2]:.5} +- {x[3]:.5}\n\
                         {'psnr:':7} {x[4]:.5} +- {x[5]:.5}\n\
                         {'mse:':7} {x[6]:.5} +- {x[7]:.5}")
                print(f'Test epoch time: {end:.4}')

            #save the model if it is the best one
            if test_metrics[-1][0] + test_metrics[-1][1] < best_loss \
               and args.rank==0:
                best_loss = test_metrics[-1][0]
                best_loss_std = test_metrics[-1][1]

                #switch to keep all the history of saved models 
                #or just the best one
                fname = os.path.join(args.dir_saved_models,
                         f'{args.model}_{task}_{epoch}.dat')
                best_model_name = fname
                bname = os.path.join(args.dir_final_test, 'best_model.txt')
                with open(bname, 'w') as f:
                    f.write(fname)
                    f.close()
                if (not args.scan) and args.rank==0:
                    print('updated best model at: ',bname)
            if args.save and args.rank==0:
                fname = os.path.join(args.dir_saved_models,
                         f'{args.model}_{task}_{channel}_{epoch}.dat')
                if not args.scan:
                    print('saved model at: %s'%fname)
            if args.rank==0:
                torch.save(model.state_dict(), fname)

        epoch += 1
    if args.rank==0:
        #loss_sum
        loss_sum = np.stack(loss_sum,1)
        fname = os.path.join(args.dir_metrics, 'loss_sum')
        np.save(fname, loss_sum)
    
        #test_epochs
        fname = os.path.join(args.dir_metrics, 'test_epochs')
        np.save(fname, test_epochs)

        #test metrics
        test_metrics = np.stack(test_metrics,1)
        fname = os.path.join(args.dir_metrics, 'test_metrics')
        np.save(fname, test_metrics)

        #time train
        fname = os.path.join(args.dir_timings, 'timings_train')
        np.save(fname, time_train)

        #time test
        fname = os.path.join(args.dir_timings, 'timings_test')
        np.save(fname, time_test)

    return best_loss, best_loss_std, best_model_name

# TODO: fix the validation loss, it must be the same of the training loss
