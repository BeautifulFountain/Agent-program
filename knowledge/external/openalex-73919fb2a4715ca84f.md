---
title: Towards Evaluating the Robustness of Neural Networks
organization: IEEE Symposium on Security and Privacy (S&P)
published_at: 2017-05-01
url: https://doi.org/10.1109/sp.2017.49
---

# Towards Evaluating the Robustness of Neural Networks

- 外部数据源：OpenAlex
- 作者：Nicholas Carlini, David Wagner
- 发布日期：2017-05-01
- DOI：10.1109/sp.2017.49
- 被引次数：9363
- 原始链接：https://doi.org/10.1109/sp.2017.49

## 摘要或检索片段

Neural networks provide state-of-the-art results for most machine learning tasks. Unfortunately, neural networks are vulnerable to adversarial examples: given an input x and any target classification t, it is possible to find a new input x' that is similar to x but classified as t. This makes it difficult to apply neural networks in security-critical areas. Defensive distillation is a recently proposed approach that can take an arbitrary neural network, and increase its robustness, reducing the success rate of current attacks' ability to find adversarial examples from 95% to 0.5%. In this paper, we demonstrate that defensive distillation does not significantly increase the robustness of neural networks by introducing three new attack algorithms that are successful on both distilled and undistilled neural networks with 100% probability. Our attacks are tailored to three distance metrics used previously in the literature, and when compared to previous adversarial example generation algorithms, our attacks are often much more effective (and never worse). Furthermore, we propose using high-confidence adversarial examples in a simple transferability test we show can also be used to break defensive distillation. We hope our attacks will be used as a benchmark in future defense attempts to create neural networks that resist adversarial examples.

## 主题分类

网络与信息安全
