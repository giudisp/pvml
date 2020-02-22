#!/usr/bin/env python3

import torch
import torchvision
import torchvision.datasets
import pvml
from pvml.pvmlnet import _LAYERS as LAYERS
import numpy as np
import argparse
import os


# Training pvmlnet with pvml would take too much time.  This is why
# pytorch is used instead.  This way it is possible to access to use a
# GPU.  At the end the learned weights are copied in the pvml CNN.


def make_pvmlnet():
    layers = []
    in_channels = 3
    for channels, size, stride in LAYERS:
        conv = torch.nn.Conv2d(in_channels, channels, size, stride)
        layers.append(conv)
        layers.append(torch.nn.ReLU())
        in_channels = channels
    layers[-1] = torch.nn.AdaptiveAvgPool2d(1)
    layers[-4:-4] = [torch.nn.Dropout2d()]
    layers[-2:-2] = [torch.nn.Dropout2d()]
    torch.nn.init.constant_(layers[0].bias, -0.5)
    model = torch.nn.Sequential(*layers)
    return model


def parse_args():
    parser = argparse.ArgumentParser(description='PVMLNET Training')
    a = parser.add_argument
    a('data', metavar='DIR', help='path to dataset')
    a('-j', '--workers', default=4, type=int, metavar='N',
      help='number of data loading workers (default: 4)')
    a('--epochs', default=90, type=int, metavar='N',
      help='number of total epochs to run')
    a('-b', '--batch-size', default=256, type=int, metavar='N',
      help='mini-batch size (default: 256)')
    a('--lr', '--learning-rate', default=0.1, type=float, metavar='LR',
      help='initial learning rate', dest='lr')
    a('--momentum', default=0.9, type=float, metavar='M',
      help='momentum')
    a('--wd', '--weight-decay', default=1e-4, type=float, metavar='W',
      help='weight decay (default: 1e-4)', dest='weight_decay')
    a('-p', '--print-freq', default=10, type=int, metavar='N',
      help='print frequency (default: 10)')
    a('--seed', default=None, type=int,
      help='seed for initializing training. ')
    a('--gpu', default=0, type=int, help='GPU id to use.')
    return parser.parse_args()


def main():
    args = parse_args()

    #----------------------------------------------------------------------
    # Setup data
    #----------------------------------------------------------------------

    tr = torchvision.transforms.Compose([
        torchvision.transforms.RandomResizedCrop(224),
        torchvision.transforms.RandomHorizontalFlip(),
        torchvision.transforms.ToTensor()
    ])

    train_dataset = torchvision.datasets.ImageNet(args.data, split='train',
                                                  transform=tr)
    train_loader = torch.utils.data.DataLoader(
        train_dataset, batch_size=args.batch_size, shuffle=True,
        num_workers=args.workers, pin_memory=True)

    tr = torchvision.transforms.Compose([
        torchvision.transforms.Resize(256),
        torchvision.transforms.CenterCrop(224),
        torchvision.transforms.ToTensor()
    ])

    val_dataset = torchvision.datasets.ImageNet(args.data, split='val',
                                                transform=tr)
    val_loader = torch.utils.data.DataLoader(
        val_dataset, batch_size=args.batch_size, shuffle=False,
        num_workers=args.workers, pin_memory=True)

    #----------------------------------------------------------------------
    # Setup models and optimizer
    #----------------------------------------------------------------------

    model = make_pvmlnet().cuda(args.gpu)
    criterion = torch.nn.CrossEntropyLoss().cuda(args.gpu)
    optimizer = torch.optim.SGD(model.parameters(), args.lr,
                                momentum=args.momentum,
                                weight_decay=args.weight_decay)

    #----------------------------------------------------------------------
    # Training loop
    #----------------------------------------------------------------------

    best_acc1 = 0
    for epoch in range(args.epochs):
        train(train_loader, model, criterion, optimizer, epoch, args)
        acc1 = validate(val_loader, model, criterion, args)
        torch.save(model, "pvmlnet_last.pt")
        if acc1 > best_acc1:
            best_acc1 = acc1
            torch.save(model, "pvmlnet_best.pt")


def train(train_loader, model, criterion, optimizer, epoch, args):
    model.train()
    for i, (images, target) in enumerate(train_loader):
        if args.gpu is not None:
            images = images.cuda(args.gpu, non_blocking=True)
        target = target.cuda(args.gpu, non_blocking=True)
        output = model(images).squeeze(-1).squeeze(-1)
        loss = criterion(output, target)
        acc1, acc5 = accuracy(output, target, topk=(1, 5))

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        if i % args.print_freq == 0:
            print("[{}] {}: {:.3f} {:.3f} {:.3f}".format(epoch, i, loss.item(), acc1.item(), acc5.item()))


def validate(val_loader, model, criterion, args):
    model.eval()
    tot1 = 0
    tot5 = 0
    count = 0
    with torch.no_grad():
        for i, (images, target) in enumerate(val_loader):
            if args.gpu is not None:
                images = images.cuda(args.gpu, non_blocking=True)
            target = target.cuda(args.gpu, non_blocking=True)
            output = model(images).squeeze(-1).squeeze(-1)
            acc1, acc5 = accuracy(output, target, topk=(1, 5))
            tot1 += acc1.item()
            tot5 += acc5.item()
            count += 1
        print(' * Acc@1 {:.3f} Acc@5 {:.3f}'.format(tot1 / count, tot5 / count))
    return tot1 / count


def accuracy(output, target, topk=(1,)):
    with torch.no_grad():
        maxk = max(topk)
        batch_size = target.size(0)
        _, pred = output.topk(maxk, 1, True, True)
        pred = pred.t()
        correct = pred.eq(target.view(1, -1).expand_as(pred))
        res = []
        for k in topk:
            correct_k = correct[:k].view(-1).float().sum(0, keepdim=True)
            res.append(correct_k.mul_(100.0 / batch_size))
        return res


if __name__ == "__main__":
    main()
    # net = make_pvmlnet()
    # x = torch.zeros(4, 3, 224, 224)
    # y = net(x)
    # print(x.size(), "->", y.size())
    # net2 = pvml.pvmlnet()
    # x = np.zeros((4, 224, 224, 3))
    # a = net2.forward(x)
    # for aa in a:
    #     print("x".join(map(str, aa.shape)))
