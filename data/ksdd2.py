#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import torch
import random
import torchvision.transforms as T

from PIL import Image
from torch.utils.data import Dataset


def c2chw(x): # change to ChannelHeightWwidth
    return x.unsqueeze(1).unsqueeze(2)


def inverse_list(list):
    """
    List to dict: index -> element
    """
    dict = {}

    for idx, x in enumerate(list):
        dict[x] = idx

    return dict


class KolektorSDD2(Dataset):
    """"
    Kolektor Surface-Defect 2 dataset

        Args:
            dataroot (string): path to the root directory of the dataset
            split    (string): data split ['train', 'test']
            scale    (string): input image scale
            debug    (bool)  : debug mode
    """

    labels = ['ok', 'defect']
    scales = {'1408x512': 1., '704x256': .5, 'half': .5}
    output_sizes = {'1408x512': (1408, 512),
                    '704x256': (704, 256),
                    'half': (704, 256)}

    # ImageNet.
    mean = (0.485, 0.456, 0.406)
    std = (0.229, 0.224, 0.225)

    def __init__(self,
                 dataroot='/path/to/dataset/'
                          'KolektorSDD2',
                 split='train', scale='half', positive_percentage=1,
                 debug=False):
        super(KolektorSDD2, self).__init__()

        self.fold = None
        self.debug = debug
        self.dataroot = dataroot

        self.split_path = None
        self.split = 'train' if 'val' == split else split 

        self.scale = scale
        self.fxy = self.scales[scale]
        self.output_size = self.output_sizes[scale]
        self.positive_percentage = positive_percentage


        self.class_to_idx = inverse_list(self.labels)
        self.classes = self.labels
        self.transform = KolektorSDD2.get_transform(output_size=self.output_size)
        self.normalize = T.Normalize(KolektorSDD2.mean, KolektorSDD2.std)

        image_cache_path = 'cache/.kolektor2_{}'.format(split)
        if os.path.isfile(image_cache_path):
            self.samples, self.masks, self.product_ids = torch.load(image_cache_path)
        else:
            self.load_imgs()
            # torch.save((self.samples, self.masks, self.product_ids), image_cache_path)
        if positive_percentage < 1 and self.split == 'train':

            m = self.masks.sum(-1).sum(-1) == 0 #if mask is empty then it means it is negative, m is 1-d tensor (N - # of images,) 
            positive_cnt = self.samples.size(0) - self.samples[m].size(0)
            positive_cnt_keep = int(positive_cnt * positive_percentage)

            #randomly pick certain percentage of positive y=1 examples
            positive_indices = [i for i, m in enumerate(self.masks) if m.sum(-1).sum(-1) != 0]
            negative_indices = [i for i, m in enumerate(self.masks) if m.sum(-1).sum(-1) == 0]
            random.shuffle(positive_indices)
            selected_indices = positive_indices[:positive_cnt_keep]+negative_indices
            self.samples = self.samples[selected_indices]
            self.masks = self.masks[selected_indices]
            self.product_ids = [self.product_ids[i] for i in selected_indices]
            # self.product_ids = [pid for flag, pid in zip(m, self.product_ids) if flag]

            print("Original number of positive samples:", positive_cnt)
            print("Number of positive samples kept:", positive_cnt_keep, ", Percentage:", positive_percentage)
            print("Total number of samples after selection:", len(self.product_ids)) #=len(selected_indices)

    def load_imgs(self):
        # Please remove this duplicated files in the official dataset:
        #   -- 10301_GT (copy).png
        #   -- 10301 (copy).png
        N = 2331 if 'train' == self.split else 1004

        self.samples = torch.Tensor(N, 3, *self.output_size).zero_() #(2331, 3, 704, 256) 
        self.masks = torch.LongTensor(N, *self.output_size).zero_() #(2331, size 704, size 256) 
        self.product_ids = []

        cnt = 0
        path = "%s/%s/" % (self.dataroot, self.split) #load sub folders
        image_list = [f for f in os.listdir(path) # get list of all images
                      if re.search(r'[0-9]+\.png$', f)] # match image name
        assert 0 < len(image_list), self.dataroot

        for img_name in image_list:
            product_id = img_name[:-4]
            img = self.transform(Image.open(path + img_name))
            lab = self.transform(
                Image.open(path + product_id + '_GT.png').convert('L'))
            self.samples[cnt] = img
            self.masks[cnt] = lab
            self.product_ids.append(product_id)
            cnt += 1

        assert N == cnt, '{} should be {}!'.format(cnt, N)


    def __getitem__(self, index):
        x = self.samples[index]
        a = self.masks[index] > 0
        if self.normalize is not None:
            x = self.normalize(x)

        if 0 == a.sum():
            y = self.class_to_idx['ok'] #0
        else:
            y = self.class_to_idx['defect'] #1

        return x, y, a, 0 # shape=4


    def __len__(self):
        return self.samples.size(0)


    @staticmethod
    def get_transform(mode='preprocess', output_size=(704, 256)):
        transform = [
            T.Resize(output_size),
            T.ToTensor()
        ]
        transform = T.Compose(transform)
        return transform


    @staticmethod
    def denorm(x):
        return x * c2chw(torch.Tensor(KolektorSDD2.std)) + c2chw(torch.Tensor(KolektorSDD2.mean))
