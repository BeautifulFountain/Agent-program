---
title: Batch Normalization: Accelerating Deep Network Training by Reducing Internal Covariate Shift
organization: arXiv (Cornell University)
published_at: 2015-02-11
url: https://doi.org/10.48550/arxiv.1502.03167
---

# Batch Normalization: Accelerating Deep Network Training by Reducing Internal Covariate Shift

- 外部数据源：OpenAlex
- 作者：Sergey Ioffe, Christian Szegedy
- 发布日期：2015-02-11
- DOI：10.48550/arxiv.1502.03167
- 被引次数：34961
- 原始链接：https://doi.org/10.48550/arxiv.1502.03167

## 摘要或检索片段

Training Deep Neural Networks is complicated by the fact that the distribution of each layer's inputs changes during training, as the parameters of the previous layers change. This slows down the training by requiring lower learning rates and careful parameter initialization, and makes it notoriously hard to train models with saturating nonlinearities. We refer to this phenomenon as internal covariate shift, and address the problem by normalizing layer inputs. Our method draws its strength from making normalization a part of the model architecture and performing the normalization for each training mini-batch. Batch Normalization allows us to use much higher learning rates and be less careful about initialization. It also acts as a regularizer, in some cases eliminating the need for Dropout. Applied to a state-of-the-art image classification model, Batch Normalization achieves the same accuracy with 14 times fewer training steps, and beats the original model by a significant margin. Using an ensemble of batch-normalized networks, we improve upon the best published result on ImageNet classification: reaching 4.9% top-5 validation error (and 4.8% test error), exceeding the accuracy of human raters.

## 主题分类

人工智能基础
