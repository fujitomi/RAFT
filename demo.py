import sys
sys.path.append('core')

import argparse
import os
import cv2
import glob
import numpy as np
import torch
from PIL import Image

from raft import RAFT
from utils import flow_viz
from utils.utils import InputPadder
from tqdm import tqdm



DEVICE = 'cuda'

def load_image(imfile):
    img = np.array(Image.open(imfile)).astype(np.uint8)
    img = torch.from_numpy(img).permute(2, 0, 1).float()
    return img[None].to(DEVICE)


def viz(img, flo, i):
    img = img[0].permute(1,2,0).cpu().numpy()
    flo = flo[0].permute(1,2,0).cpu().numpy()
    
    # map flow to rgb image
    flo = flow_viz.flow_to_image(flo)
    img_flo = np.concatenate([img, flo], axis=0)

    #import matplotlib.pyplot as plt
    #plt.imshow(img_flo / 255.0)
    #plt.show()

    #cv2.imshow('image', img_flo[:, :, [2,1,0]]/255.0)
    #cv2.waitKey()

    output_dir = './images'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    cv2.imwrite(os.path.join(output_dir, "{:05d}.png".format(i)), img_flo[:, :, [2,1,0]])
    #print(img_flo.shape) #[H, W, 3]



def demo(args):
    model = torch.nn.DataParallel(RAFT(args))
    model.load_state_dict(torch.load(args.model))

    model = model.module
    model.to(DEVICE)
    model.eval()

    with torch.no_grad():
        images = glob.glob(os.path.join(args.path, '*.png')) + \
                 glob.glob(os.path.join(args.path, '*.jpg'))
        
        images = sorted(images)
        i = 0
        firstIter = True
        for imfile1, imfile2 in tqdm(zip(images[:-args.frame_len], images[args.frame_len:])):
            image1 = load_image(imfile1)
            image2 = load_image(imfile2)

            padder = InputPadder(image1.shape)
            image1, image2 = padder.pad(image1, image2)

            flow_low, flow_up = model(image1, image2, iters=20, test_mode=True)
            if args.filter_type=='mean':
                if firstIter: 
                    tmp_flows = torch.zeros_like(flow_up).repeat(args.filter_size,1,1,1)
                    firstIter = False
                tmp_flows[i%args.filter_size] = flow_up[0]
                mean_flow = tmp_flows.mean(dim=0, keepdim=True)
                viz(image1, mean_flow, i)
            elif args.filter_type=='median':
                if firstIter: 
                    tmp_flows = torch.zeros_like(flow_up).repeat(args.filter_size,1,1,1)
                    firstIter = False
                tmp_flows[i%args.filter_size] = flow_up[0]
                print(tmp_flows.shape)
                index = tmp_flows.pow(2).sum(dim=3, keepdim=True).median(dim=0, keepdim=True)[1]
                print(index.shape)
                median_flow = tmp_flows.gather(dim=0, index = index.repeat(1,1,1,2))
                viz(image1, median_flow, i)

            else: viz(image1, flow_up, i)
            i += 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', help="restore checkpoint")
    parser.add_argument('--path', help="dataset for evaluation")
    parser.add_argument('--small', action='store_true', help='use small model')
    parser.add_argument('--mixed_precision', action='store_true', help='use mixed precision')
    parser.add_argument('--alternate_corr', action='store_true', help='use efficent correlation implementation')
    parser.add_argument('--frame_len', type=int, default=1, help='frame length of 2 images in flow estimation')
    parser.add_argument('--filter_type', type=str, default='None', help='use small model')
    parser.add_argument('--filter_size', type=int, default=9, help='filter window size')

    args = parser.parse_args()

    demo(args)
