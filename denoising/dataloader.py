import os
import torch

class CropLoader(torch.utils.data.Dataset):
    def __init__(self, data_dir):
        fname = os.path.join(data_dir, 'clear_crops/readout_train')
        readout_clear = torch.load(fname)

        fname = os.path.join(data_dir, 'clear_crops/collection_train')
        collection_clear = torch.load(fname)

        fname = os.path.join(data_dir, 'noised_crops/readout_train')
        readout_noise = torch.load(fname)

        fname = os.path.join(data_dir, 'noised_crops/collection_train')
        collection_noise = torch.load(fname)

        self.clear_crops = torch.cat([collection_clear, readout_clear])
        self.noised_crops = torch.cat([collection_noise, readout_noise])

        #shape: (batch, #channel,width, height)
        #with #channel==1
        self.clear_crops = self.clear_crops.unsqueeze(1)
        self.noised_crops = self.noised_crops.unsqueeze(1)
     
    def __len__(self):
        return len(self.noised_crops)
    def __getitem__(self, index):
        return self.clear_crops[index], self.noised_crops[index]

class PlaneLoader(torch.utils.data.Dataset):
    def __init__(self, data_dir, file):

        fname = os.path.join(data_dir, 'clear_planes/%s'%file)
        self.clear_planes = torch.load(fname).unsqueeze(1)

        fname = os.path.join(data_dir, 'noised_planes/%s'%file)
        self.noised_planes = torch.load(fname).unsqueeze(1)
     
    def __len__(self):
        return len(self.noised_planes)
    def __getitem__(self, index):
        return self.clear_planes[index], self.noised_planes[index]