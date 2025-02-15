import torch
import torch.nn as nn
import torchvision
import torchvision.transforms as transforms

from functools import partial
from time import time
from tqdm import tqdm
import argparse
import trainer
import numpy as np
import os

import timm
from timm.models import create_model
from timm.data.mixup import Mixup
from timm.data.random_erasing import RandomErasing
from timm.data.auto_augment import rand_augment_transform
from timm.scheduler.cosine_lr import CosineLRScheduler
from timm.models.layers import trunc_normal_, DropPath
from timm.loss import LabelSmoothingCrossEntropy, SoftTargetCrossEntropy
from RandAugment import RandAugment

device = torch.device("cuda")

train_losses = []
train_accs = []
test_losses = []
test_accs = []
save_path = './model/'

s = time()

def main(args):
    use_amp = args.amp

    mean = [0.4914, 0.4822, 0.4465]
    std = [0.2023, 0.1994, 0.2010]

    train_transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.RandomCrop(32, padding=4),
        transforms.RandomHorizontalFlip(),
        transforms.Resize((224,224)),
        transforms.Normalize(mean, std),
    ])
    test_transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Resize((224,224)),
        transforms.Normalize(mean, std),
    ])

    if args.dataset == 'cifar10':
        train_dataset = torchvision.datasets.CIFAR10("./data", train=True, transform=train_transform, download=True)
        test_dataset = torchvision.datasets.CIFAR10("./data", train=False, transform=test_transform, download=False)
        class_names = train_dataset.classes
        criterion = torch.nn.CrossEntropyLoss()

    elif args.dataset == 'cifar100':
        train_dataset = torchvision.datasets.CIFAR100("./data", train=True, transform=train_transform, download=True)
        test_dataset = torchvision.datasets.CIFAR100("./data", train=False, transform=test_transform, download=False)
        class_names = train_dataset.classes        
        criterion = torch.nn.CrossEntropyLoss()

    print(class_names)
    print('Class:', len(class_names))

    train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=8, pin_memory=True, drop_last=True)
    test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False, num_workers=8, pin_memory=True, drop_last=False)

    model = create_model("vit_tiny_patch16_224", pretrained=True, num_classes=len(class_names)) 
    # model = create_model("vit_small_patch16_224", pretrained=True, num_classes=len(class_names)) 
    # model = create_model("vit_base_patch16_224", pretrained=True, num_classes=len(class_names)) 
    # model = create_model("vit_large_patch16_224", pretrained=True, num_classes=len(class_names)) 
    model.to('cuda')

    # 最後のTransformer Encoderブロックは凍結する
    for param in model.parameters():
        param.requires_grad = False

    # 分類層（head）のみ学習可能にする
    for param in model.head.parameters():
        param.requires_grad = True

    # optimizerの設定
    optimizer = torch.optim.AdamW(model.head.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    lr_scheduler = CosineLRScheduler(optimizer=optimizer, t_initial=args.epoch, 
        warmup_t=args.warmup_t, warmup_lr_init=args.warmup_lr_init, warmup_prefix=True)
    scaler = torch.cuda.amp.GradScaler(enabled=use_amp)

    # 学習対象のパラメータのみを可視化
    param_count = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"Total number of trainable parameters: {param_count}")

    for epoch in range(args.epoch):
        train_loss, train_count = trainer.train(device, train_loader, model, criterion, optimizer, lr_scheduler, scaler, use_amp, epoch)
        # train_loss, train_count = trainer.saves_train(device, train_loader, model, criterion, optimizer, lr_scheduler, scaler, use_amp, epoch)
        
        test_loss, test_count = trainer.test(device, test_loader, model)

        train_loss = (train_loss/len(train_loader))
        train_acc = (train_count/len(train_loader.dataset))
        test_loss = (test_loss/len(test_loader))
        test_acc = (test_count/len(test_loader.dataset))

        print(f"epoch: {epoch+1},\
                train loss: {train_loss},\
                train accuracy: {train_acc}\
                test loss: {test_loss},\
                test accuracy: {test_acc}")

        train_losses.append(train_loss)
        train_accs.append(train_acc)
        test_losses.append(test_loss)
        test_accs.append(test_acc)

    e = time()
    print('Elapsed time is ',e-s)

if __name__=='__main__':

    parser=argparse.ArgumentParser()
    parser.add_argument('--epoch', type=int, default=10)
    parser.add_argument('--batch_size', type=int, default=32)
    parser.add_argument("--lr", type=int, default=1e-4)
    parser.add_argument("--weight_decay", type=int, default=0.05)
    parser.add_argument("--warmup_t", type=int, default=5)
    parser.add_argument("--warmup_lr_init", type=int, default=1e-5)
    parser.add_argument("--dataset", type=str, default="cifar10")
    parser.add_argument('--amp', action='store_true')
    args=parser.parse_args()
    main(args)
