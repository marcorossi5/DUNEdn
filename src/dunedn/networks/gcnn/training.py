""" This module provides functions for CNN and GCNN networks training and loading."""
import logging
from pathlib import Path
import torch
from .gcnn_dataloading import TilingDataset
from .gcnn_net import GcnnNet
from dunedn import PACKAGE
from dunedn.training.losses import get_loss
from dunedn.training.metrics import DN_METRICS

logger = logging.getLogger(PACKAGE + ".gcnn")


def load_and_compile_gcnn_network(
    msetup: dict, checkpoint_filepath: Path = None
) -> GcnnNet:
    """Loads CNN or GCNN network.

    Parameters
    ----------
    msetup: dict
        The model setup dictionary.
    checkpoint_filepath: Path
        The `.pth` checkpoint containing network weights to be loaded.

    Returns
    -------
    network: GcnnNet
        The loaded neural network.
    """
    network = GcnnNet(**msetup["net_dict"])

    if checkpoint_filepath:
        logger.info(f"Loading weights at {checkpoint_filepath}")
        state_dict = torch.load(checkpoint_filepath, map_location=torch.device("cpu"))
        # new_state_dict = make_dict_compatible(state_dict)
        network.load_state_dict(state_dict)

    # loss
    loss = get_loss(msetup["loss_fn"])()

    # optimizer
    optimizer = torch.optim.Adam(list(network.parameters()), msetup["lr"])

    network.compile(loss, optimizer, DN_METRICS)

    return network


def gcnn_training(modeltype: str, setup: dict):
    """GCNN network training.

    Parameters
    ----------
    modeltype: str
        The model to be trained. Available options: cnn | gcnn.
    setup: dict
        Settings dictionary.
    """
    # model loading
    assert modeltype in ["cnn", "gcnn"]
    msetup = setup["model"][modeltype]
    network = load_and_compile_gcnn_network(msetup, msetup["ckpt"])

    # TODO: remove channel (collection | induction) hard coding
    # data loading
    data_folder = setup["dataset"]["data_folder"]

    train_generator = TilingDataset(
        data_folder / "train/evts",
        batch_size=msetup["batch_size"],
        crop_size=msetup["crop_size"],
        has_target=True,
    )

    val_generator = TilingDataset(
        data_folder / "val/evts",
        batch_size=msetup["batch_size"],
        crop_size=msetup["crop_size"],
        has_target=True,
    )

    # training
    network.fit(
        train_generator,
        epochs=setup["model"]["epochs"],
        val_generator=val_generator,
        dev=setup["dev"],
    )

    # testing
    logger.info("Stop training, now testing")
    test_generator = TilingDataset(
        data_folder / "test/evts",
        batch_size=msetup["batch_size"],
        crop_size=msetup["crop_size"],
        has_target=True,
    )
    _, logs = network.predict(test_generator)
    network.metrics_list.print_metrics(logger, logs)
