import sys
import os
import argparse
import numpy as np
import time as tm
import matplotlib.pyplot as plt
import matplotlib as mpl

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def training_metrics(warmup):
    dir_name = f'./denoising/output/CNN_{warmup}_final/metrics/'
    dir_name_gc = f'./denoising/output/GCNN_{warmup}_final/metrics/'
    
    fname = dir_name + 'loss_sum.npy'
    loss = np.load(fname)[0]
    # shape (1. train_epochs)

    fname = dir_name + 'test_epochs.npy'
    val_epochs = np.load(fname)
    # shape (val_epochs,)

    fname = dir_name + 'test_metrics.npy'    
    val_metrics = np.load(fname)
    # shape (8, val_epochs)
    # couples of mean values and uncertainties of:
    # loss (ssim + l2), ssim, pSNR, MSE

    fname = dir_name_gc + 'loss_sum.npy' 
    loss_gc = np.load(fname)[0]

    fname = dir_name_gc + 'test_epochs.npy' 
    val_epochs_gc = np.load(fname)

    fname = dir_name_gc + 'test_metrics.npy' 
    val_metrics_gc = np.load(fname)

    return ([loss, loss_gc],
            [val_epochs, val_epochs_gc],
            [val_metrics, val_metrics_gc])


def training_timings(warmup):
    dir_name = f'./denoising/output/CNN_{warmup}_final/timings/'
    dir_name_gc = f'./denoising/output/GCNN_{warmup}_final/timings/'
    
    fname = dir_name + 'timings_train.npy'
    timings_train = np.load(fname)
    # shape (epochs,)

    fname = dir_name + 'timings_test.npy'
    timings_val = np.load(fname)
    # shape (val_epochs,)

    fname = dir_name_gc + 'timings_train.npy'
    timings_train_gc = np.load(fname)

    fname = dir_name_gc + 'timings_test.npy'
    timings_val_gc = np.load(fname)

    return ([timings_train, timings_train_gc],
            [timings_val, timings_val_gc])

def set_ticks(ax, axis, start=None, end=None,
              num_maj=None, div=5, d=0, p=False):
    """
    Set both major and minor axes ticks in the logarithmical scale
    Parameters:
        ax: matplotlib.axes.Axes object
        axis: 1 y axis, 0 x axis
        start: int, leftmost tick
        end: int, rightmost tick
        num_maj: int, number of major ticks
        div: int, how to partition interval between maj ticks
        d: int, decimal digits axis labels
    """
    #to divide each in 5 parts: num_min = (num_maj - 1)*5 -1
    rng = end - start
    ticks = [i*rng/(num_maj-1) + start for i in range(num_maj)]
    labels = list(map(lambda x: r'$%s$'%format(x, f'.{d}f'), ticks))
    num_min = (num_maj -1)*div + 1 
    ticks_min = [i*rng/(num_min-1) + start for i in range(num_min)]
    if p:
        print(ticks)
        print(labels)
        print(ticks_min)

    if axis == 'x':
        ax.xaxis.set_major_locator(mpl.ticker.FixedLocator(ticks))
        ax.xaxis.set_major_formatter(mpl.ticker.FixedFormatter(labels))
        ax.xaxis.set_minor_locator(mpl.ticker.FixedLocator(ticks_min))
        ax.xaxis.set_minor_formatter(mpl.ticker.NullFormatter())
        return ax

    ax.yaxis.set_major_locator(mpl.ticker.FixedLocator(ticks))
    ax.yaxis.set_major_formatter(mpl.ticker.FixedFormatter(labels))
    ax.yaxis.set_minor_locator(mpl.ticker.FixedLocator(ticks_min))
    ax.yaxis.set_minor_formatter(mpl.ticker.NullFormatter())
    return ax


def training_plots():
    mpl.rcParams['text.usetex'] = True
    mpl.rcParams['savefig.format'] = 'pdf'
    mpl.rcParams['figure.titlesize'] = 20
    mpl.rcParams['axes.titlesize'] = 17
    mpl.rcParams['ytick.labelsize'] = 17
    mpl.rcParams['xtick.labelsize'] = 17
    mpl.rcParams['legend.fontsize'] = 14

    loss, val_epochs, val_metrics = training_metrics('roi')
    
    epochs = [i for i in range(len(loss[0]))]

    fig = plt.figure()
    fig.suptitle('Training Loss')
    
    gs = fig.add_gridspec(nrows=1, ncols=2, wspace=0.2)
    ax = fig.add_subplot(gs[0])
    ax.set_title('Training')
    ax.set_ylabel(r'Loss: $SSIM + MSE$')
    ax.plot(epochs, loss[0], label='cnn', color='#ff7f0e')
    ax.plot(epochs, loss[1], label='gcnn', color='b')
    ax.set_xlim([0,100])
    ax = set_ticks(ax,'x', 0, 100, 6)
    ax.set_ylim([0,.7])
    ax = set_ticks(ax,'y', 0, .7, 5, d=1)
    ax.tick_params(axis='x', which='both', direction='in',
                   top=True, labeltop=False,
                   bottom=True, labelbottom=True)
    ax.tick_params(axis='y', which='both', direction='in',
                   right=True, labelright=False,
                   left=True, labelleft=True)
    ax.legend(frameon=False)

    ax = fig.add_subplot(gs[1])
    ax.set_title('Validation')
    ax.errorbar(val_epochs[1], val_metrics[0][0], yerr=val_metrics[0][1],
                label='cnn', linestyle='--', color='#ff7f0e', marker='s')
    ax.errorbar(val_epochs[1], val_metrics[1][0], yerr=val_metrics[1][1],
                label='gcnn', linestyle='--', color='b', marker='^')
    ax.set_xlim([0,100])
    ax = set_ticks(ax,'x', 0, 100, 6)
    ax.set_ylim([0,7])
    ax = set_ticks(ax,'y', 0, 7, 8)
    ax.tick_params(axis='x', which='both', direction='in',
                   top=True, labeltop=False,
                   bottom=True, labelbottom=True)
    ax.tick_params(axis='y', which='both', direction='in',
                   right=True, labelright=True,
                   left=True, labelleft=False)

    plt.savefig(f'denoising/benchmarks/results/training_loss_roi.pdf',
                bbox_inches='tight', dpi=250)
    plt.close()

    ##########################################################################

    timings_train, timings_val = training_timings('roi')

    fig = plt.figure()
    fig.suptitle('Timings')
    gs = fig.add_gridspec(nrows=1, ncols=2, wspace=0.2)

    ax = fig.add_subplot(gs[0])
    ax.set_title('Training')
    ax.set_ylabel('Time [s]')
    ax.set_xlabel('Epoch')
    ax.plot(epochs, timings_train[0], label='cnn', color='#ff7f0e')
    ax.plot(epochs, timings_train[1], label='gcnn', color='b')
    ax.set_xlim([0,100])

    ax = set_ticks(ax,'x', 0, 100, 6)
    ax.set_ylim([0,100])
    ax = set_ticks(ax,'y', 0, 100, 6)
    ax.tick_params(axis='x', which='both', direction='in',
                   top=True, labeltop=False,
                   bottom=True, labelbottom=True)
    ax.tick_params(axis='y', which='both', direction='in',
                   right=True, labelright=False,
                   left=True, labelleft=True)
    ax.legend(frameon=False)

    ax = fig.add_subplot(gs[1])
    ax.set_title('Validation')
    ax.set_xlabel('Epoch')
    ax.plot(val_epochs[0], timings_val[0], label='cnn',
            color='#ff7f0e', linestyle='--')

    ax.plot(val_epochs[1], timings_val[1], label='gcnn',
            color='b', linestyle='--')
    ax.set_xlim([5,100])
    ax.set_ylim([0,80])
    ax = set_ticks(ax,'y', 0, 80, 5)

    rng = 95
    ticks = [5,35,65,95]
    labels = list(map(lambda x:r'$%.0f$'%x, ticks))
    ticks_min = [i for i in range(5,101,5)]

    ax.xaxis.set_major_locator(mpl.ticker.FixedLocator(ticks))
    ax.xaxis.set_major_formatter(mpl.ticker.FixedFormatter(labels))
    ax.xaxis.set_minor_locator(mpl.ticker.FixedLocator(ticks_min))
    ax.xaxis.set_minor_formatter(mpl.ticker.NullFormatter())

    ax.tick_params(axis='x', which='both', direction='in',
                   top=True, labeltop=False,
                   bottom=True, labelbottom=True)
    ax.tick_params(axis='y', which='both', direction='in',
                   right=True, labelright=True,
                   left=True, labelleft=False)

    plt.savefig(f'denoising/benchmarks/results/timings_roi.pdf',
                bbox_inches='tight', dpi=250)
    plt.close()


def testing_plots():
    pass


def main():
    training_plots()

    testing_plots()


if __name__ == '__main__':
    start = tm.time()
    main()
    print(f'Program done in {tm.time()-start}')
