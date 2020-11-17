import os
from datetime import datetime as dtm

class Args:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.patch_size = (32,32)
        self.crop_p = 0.99 # signal to noise crops percentage

        #argparser
        self.test_batch_size = self.batch_size*2 # if 'gcnn' in self.model else self.batch_size*4
        self.num_workers = 8

        #model parameters
        self.a = 0.84
        self.k = 8
        self.input_channels = 1
        self.hidden_channels = 32
        
        #logs
        self.plot_dataset = False
        self.plot_acts = True

        self.epoch_log = 1
        self.epoch_test_start = 0
        self.epoch_test = 1

        self.t = 0.5

        self.load = False if (self.load_path is None) else True
        self.load_epoch = 100

        self.save = True
        #self.epoch_save = 5

    def build_directories(self, build=True):
        #build directories
        t = dtm.now().strftime("%y%m%d_%H%M%S") if self.out_name is None \
            else self.out_name
        self.dir_output = f"./denoising/output/{t}"

        def mkdir_fn(name, build):
            dirname = os.path.join(self.dir_output, name)
            if not os.path.isdir(dirname) and build:
                os.makedirs(dirname)
            return dirname
        mkdir_fn("", build)
        self.dir_timings = mkdir_fn("timings", build)
        self.dir_testing = mkdir_fn("testing", build)
        self.dir_final_test = mkdir_fn("final_test", build)
        self.dir_metrics = mkdir_fn("metrics", build)
        self.dir_saved_models = mkdir_fn("model_save", build)
