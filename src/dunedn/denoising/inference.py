# This file is part of DUNEdn by M. Rossi
"""
    This module contains the wrapper function for the ``dunedn inference``
    command.
"""
from copy import deepcopy
import numpy as np
import torch
from pathlib import Path
from dunedn.denoising.hitreco import DnModel, compute_metrics

THRESHOLD = 3.5  # the ADC threshold below which the output is put to zero
# TODO: move this into some dunedn config file


def add_arguments_inference(parser):
    """
    Adds inference subparser arguments.

    Parameters
    ----------
        - parser: ArgumentParser, inference subparser object
    """
    parser.add_argument(
        "-i",
        type=Path,
        help="path to the input event file",
        required=True,
        metavar="INPUT",
        dest="input",
    )
    parser.add_argument(
        "-o",
        type=Path,
        help="path to the output event file",
        required=True,
        metavar="OUTPUT",
        dest="output",
    )
    parser.add_argument(
        "-m",
        help="model name. Valid options: (uscg|gcnn|cnn|id)",
        required=True,
        metavar="MODEL",
        dest="modeltype",
    )
    parser.add_argument(
        "--model_path",
        type=Path,
        help="(optional) path to directory with saved model",
        default=None,
        dest="ckpt",
    )
    parser.set_defaults(func=inference)


def inference(args):
    """
    Wrapper inference function.

    Parameters
    ----------
        - args: NameSpace object, parsed from command line or from code. It
                should contain input, output and model attributes.
    """
    args = vars(args)
    args.pop("func")
    inference_main(**args)


def inference_main(input, output, modeltype, ckpt):
    """
    Inference main function. Loads an input event from file, makes inference and
    saves the ouptut. Eventually returns the output array.

    Parameters
    ----------
        - input: Path, path to the input event file
        - output: Path, path to the output event file
        - modeltype: str, model name. Available options: uscg|gcnn|cnn|id
        - ckpt: path to directory with saved model

    Returns
    -------
        - np.array, ouptut event of shape=(nb wires, nb tdc ticks)
    """
    print(f"Denoising event at {input}")
    evt = np.load(input)[:, 2:]
    model = DnModel(modeltype, ckpt)
    dev = "cuda:0" if torch.cuda.is_available() else "cpu"

    evt_dn = model.inference(evt, dev)
    np.save(output, evt_dn)
    print(f"Saved output event at {output}.npy")
    return evt_dn


def compare_performance_dn(evt_dn, target):
    """
    Computes perfromance metrics between denoising inference output and ground
    truth labels.

    Parameters
    ----------
        - evt_roi: np.array, denoised event of shape=(nb wires, nb tdc ticks)
        - target: np.array, ground truth labels of shape=(nb wires, nb tdc ticks)
    """
    mask = np.abs(evt_dn) <= THRESHOLD
    # bind evt_dn variable to a copy to prevent in place substitution
    evt_dn = deepcopy(evt_dn)
    evt_dn[mask] = 0
    compute_metrics(evt_dn, target, "dn")


def compare_performance_roi(evt_roi, target):
    """
    Computes perfromance metrics between ROI inference output and ground truth
    labels.

    Parameters
    ----------
        - evt_roi: np.array, event ROI selection of shape=(nb wires, nb tdc ticks)
        - target: np.array, ground truth labels of shape=(nb wires, nb tdc ticks)
    """
    mask = np.abs(evt_roi) <= THRESHOLD
    # bind target variable to a copy to prevent in place substitution
    target = deepcopy(target)
    target[mask] = 0
    target[~mask] = 1
    compute_metrics(evt_roi, target, "roi")


# inputs: the input event filename, the output event filename, the saved model
# TODO: think about the possibility to use un un-trained model
# ouptuts: the file to save
# this module should load an event, make inference and save output
# TODO: in the benchmark folder, write an example exploiting this module, that loads
# some event and computes the metrics with the compute_metrics function.
# TODO: decide what to do with the ROI module (drop it? or leave it for future enhancements?