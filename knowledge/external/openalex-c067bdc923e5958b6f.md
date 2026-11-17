---
title: Hierarchical Text-Conditional Image Generation with CLIP Latents
organization: arXiv (Cornell University)
published_at: 2022-04-13
url: https://doi.org/10.48550/arxiv.2204.06125
---

# Hierarchical Text-Conditional Image Generation with CLIP Latents

- 外部数据源：OpenAlex
- 作者：Ramesh, Aditya, Prafulla Dhariwal, Alex Nichol, Casey Chu, Mark I-Cheng Chen
- 发布日期：2022-04-13
- DOI：10.48550/arxiv.2204.06125
- 被引次数：8874
- 原始链接：https://doi.org/10.48550/arxiv.2204.06125

## 摘要或检索片段

Contrastive models like CLIP have been shown to learn robust representations of images that capture both semantics and style. To leverage these representations for image generation, we propose a two-stage model: a prior that generates a CLIP image embedding given a text caption, and a decoder that generates an image conditioned on the image embedding. We show that explicitly generating image representations improves image diversity with minimal loss in photorealism and caption similarity. Our decoders conditioned on image representations can also produce variations of an image that preserve both its semantics and style, while varying the non-essential details absent from the image representation. Moreover, the joint embedding space of CLIP enables language-guided image manipulations in a zero-shot fashion. We use diffusion models for the decoder and experiment with both autoregressive and diffusion models for the prior, finding that the latter are computationally more efficient and produce higher-quality samples.

## 主题分类

多模态学习
