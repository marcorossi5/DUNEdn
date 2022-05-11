"""
    This module contains utility functions for the inference step.
"""
import logging
import numpy as np
from dunedn.configdn import PACKAGE
from dunedn.networks.gcnn.training import load_and_compile_gcnn_network
from dunedn.networks.gcnn.gcnn_dataloading import GcnnPlanesDataset
from dunedn.geometry.helpers import evt2planes, planes2evt
from dunedn.networks.uscg.training import load_and_compile_uscg_network
from dunedn.networks.uscg.uscg_dataloading import UscgPlanesDataset
from dunedn.training.metrics import DN_METRICS

logger = logging.getLogger(PACKAGE + ".inference")


def get_models(task, modeltype, ckpt, msetup, dev):
    load_fn = (
        load_and_compile_uscg_network
        if modeltype == "uscg"
        else load_and_compile_gcnn_network
    )
    if ckpt is not None:
        ckpt_induction = ckpt / "induction" / f"{ckpt.name}_{task}_induction.pth"
        ckpt_collection = ckpt / "collection" / f"{ckpt.name}_{task}_collection.pth"
    else:
        ckpt_induction = None
        ckpt_collection = None
    inetwork = load_fn("induction", msetup, dev, ckpt_induction)
    cnetwork = load_fn("collection", msetup, dev, ckpt_collection)
    return inetwork, cnetwork


def get_onnx_models(task, modeltype, ckpt):
    from dunedn.networks.onnx.onnx_gcnn_net import OnnxGcnnNetwork

    fname = ckpt / f"induction/{modeltype}_{task}.onnx"
    logger.debug(f"Loading onnx model at {fname}")
    inetwork = OnnxGcnnNetwork(
        fname.as_posix(),
        DN_METRICS,
        # providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    fname = ckpt / f"collection/{modeltype}_{task}.onnx"
    logger.debug(f"Loading onnx model at {fname}")
    cnetwork = OnnxGcnnNetwork(
        fname.as_posix(),
        DN_METRICS,
        # providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    return inetwork, cnetwork


class BaseModel:
    """
    Mother class for inference model.
    """

    def __init__(
        self, setup, modeltype, task, ckpt=None, dev="cpu", should_use_onnx=False
    ):
        """
        Parameters
        ----------
        setup: dict
            Settings dictionary.
        modeltype: str
            Available options cnn | gcnn | uscg.
        task: str
            Available options dn | roi.
        ckpt: Path
            Saved checkpoint path. If None, an un-trained model will be used.
        dev: str
            Device hosting computation.
        should_use_onnx: bool
            Wether to use ONNX exported model.
        """
        self.setup = setup
        self.modeltype = modeltype
        self.task = task
        self.ckpt = ckpt
        self.dev = dev
        self.should_use_onnx = should_use_onnx

        msetup = setup["model"][self.modeltype]

        if should_use_onnx:
            if modeltype == "uscg":
                raise NotImplementedError(
                    "Cannot call with onnx inference with USCG network."
                )
            self.inetwork, self.cnetwork = get_onnx_models(
                self.task, self.modeltype, self.ckpt
            )
        else:
            self.inetwork, self.cnetwork = get_models(
                self.task, self.modeltype, self.ckpt, msetup, self.dev
            )

        gen_kwargs = {
            "task": setup["task"],
            "dsetup": setup["dataset"],
        }
        data_fn = UscgPlanesDataset if modeltype == "uscg" else GcnnPlanesDataset
        self.collection_generator = lambda planes: data_fn(
            planes,
            batch_size=msetup["test_batch_size"],
            channel="collection",
            **gen_kwargs,
        )
        self.induction_generator = lambda planes: data_fn(
            planes,
            batch_size=msetup["test_batch_size"],
            channel="induction",
            **gen_kwargs,
        )

    def predict(self, event: np.ndarray) -> np.ndarray:
        """Interface for model prediction on pDUNE event.

        Parameters
        ----------
        event: np.ndarray
            Event input array of shape=(nb wires, nb tdc ticks).

        Returns
        -------
        np.ndarray
            Denoised event of shape=(nb wires, nb tdc ticks).
        """
        logger.debug("Starting inference on event")
        iplanes, cplanes = evt2planes(event)

        idataset = self.induction_generator(iplanes)
        cdataset = self.collection_generator(cplanes)

        if self.should_use_onnx:
            iout = self.inetwork.predict(idataset)
            cout = self.cnetwork.predict(cdataset)
        else:
            iout = self.inetwork.predict(idataset, self.dev, no_metrics=True)
            cout = self.cnetwork.predict(cdataset, self.dev, no_metrics=True)

        return planes2evt(iout, cout)

    def onnx_export(self, output_dir=None):
        """
        Exports the model to onnx format.

        Parameters
        ----------
        output_dir: Path
            The directory to save the onnx files.
        """
        if output_dir is None:
            output_dir = self.ckpt

        logger.debug(f"Exporting onnx model")

        # export induction
        fname = output_dir / f"induction/{self.modeltype}_{self.task}.onnx"
        self.inetwork.onnx_export(fname)
        logger.info(f"Saved onnx module at: {fname}")

        # export collection
        fname = output_dir / f"collection/{self.modeltype}_{self.task}.onnx"
        self.cnetwork.onnx_export(fname)
        logger.info(f"Saved onnx module at: {fname}")


class DnModel(BaseModel):
    """Wrapper class for denoising model."""

    def __init__(self, setup, modeltype, ckpt=None, dev="cpu", should_use_onnx=False):
        """
        Parameters
        ----------
        modeltype: str
            Valid options: "cnn" | "gcnn" | "usgc".
        ckpt: Path
            Saved checkpoint path. The path should point to a folder containing
            a collection and an induction .pth file. If `None`, an un-trained
            model will be used.
        dev: str
            Device hosting the computation.
        should_use_onnx: bool
            Wether to use ONNX exported model.
        """
        super(DnModel, self).__init__(
            setup, modeltype, "dn", ckpt, dev, should_use_onnx
        )


class RoiModel(BaseModel):
    """Wrapper class for ROI selection model."""

    def __init__(self, setup, modeltype, ckpt=None, dev="cpu", should_use_onnx=False):
        """
        Parameters
        ----------
        modeltype: str
            Valid options: "cnn" | "gcnn" | "usgc".
        ckpt: Path
            Saved checkpoint path. If None, an un-trained model will be used.
        dev: str
            Device hosting the computation.
        should_use_onnx: bool
            Wether to use ONNX exported model.
        """
        super(RoiModel, self).__init__(
            setup, modeltype, "roi", ckpt, dev, should_use_onnx
        )


class DnRoiModel:
    """Wrapper class for denoising and ROI selection model."""

    def __init__(
        self,
        setup,
        modeltype,
        roi_ckpt=None,
        dn_ckpt=None,
        dev="cpu",
        should_use_onnx=False,
    ):
        """
        Parameters
        ----------
        modeltype: str
            Valid options: "cnn" | "gcnn" | "usgc".
        ckpt: Path
            Saved checkpoint path. If None, an un-trained model will be used.
        dev: str
            Device hosting the computation.
        """
        self.roi = RoiModel(setup, modeltype, roi_ckpt, dev, should_use_onnx)
        self.dn = DnModel(setup, modeltype, dn_ckpt, dev, should_use_onnx)
