📘 第六段：EM算法与隐变量模型（教材级扩展）

（对应PDF：算法篇-EM算法） ￼

⸻

一、问题背景：不完备数据与隐变量

在现实中，很多问题具有如下特点：

数据不完整 / 存在隐藏结构 / 标签不可见

例如：
	•	聚类：不知道类别标签
	•	推荐系统：用户兴趣不可见
	•	NLP：语义结构是隐含的

👉 数学表达：

观测数据：X
隐变量：Z

完整数据：

(X, Z)

但我们只能看到：

X

⸻

二、隐变量模型的目标

目标是最大化似然：

$$
P(X|\theta) = \sum_Z P(X, Z|\theta)
$$

👉 难点：
	•	隐变量 Z 不可见
	•	求和复杂

⸻

三、EM算法的核心思想

EM = Expectation-Maximization

👉 核心思想：

通过“猜测隐变量 + 优化参数”交替进行

⸻

3.1 算法流程

E步（Expectation）

计算隐变量的期望：

$$
Q(Z) = P(Z|X, \theta^{(t)})
$$

⸻

M步（Maximization）

更新参数：

$$
\theta^{(t+1)} = \arg\max \mathbb{E}_{Z}[ \log P(X,Z|\theta)]
$$

⸻

👉 迭代：

E步（估计隐变量） → M步（优化参数） → 重复


⸻

四、EM算法的推导核心（重要理解）

4.1 对数似然

目标：

$$
\log P(X|\theta)
$$

由于：

$$
P(X|\theta) = \sum_Z P(X,Z|\theta)
$$

直接优化困难

⸻

4.2 引入下界（Jensen不等式）

构造：

$$
\log P(X|\theta) \ge \mathbb{E}_Q[\log P(X,Z|\theta)] - \mathbb{E}_Q[\log Q(Z)]
$$

👉 EM本质：

不断提升这个下界（ELBO思想雏形）

⸻

五、经典应用：高斯混合模型（GMM）

5.1 模型定义

假设数据由多个高斯分布生成：

$$
P(x) = \sum_{k=1}^{K} \pi_k \mathcal{N}(x|\mu_k, \Sigma_k)
$$

其中：
	•	\pi_k：混合系数
	•	\mu_k：均值
	•	\Sigma_k：协方差

⸻

5.2 隐变量定义

引入：

z_i \in \{1,2,...,K\}

表示样本属于哪个高斯分布

⸻

5.3 E步（计算责任度）

$$
\gamma_{ik}=\frac{\pi_k \mathcal{N}(x_i|\mu_k,\Sigma_k)}{\sum_j \pi_j \mathcal{N}(x_i|\mu_j,\Sigma_j)}
$$

👉 含义：
	•	样本属于第k类的概率

⸻

5.4 M步（参数更新）

更新：

$$
\mu_k = \frac{\sum \gamma_{ik} x_i}{\sum \gamma_{ik}}
$$

$$
\Sigma_k = \frac{\sum \gamma_{ik}(x_i - \mu_k)^2}{\sum \gamma_{ik}}
$$

$$
\pi_k = \frac{1}{n} \sum \gamma_{ik}
$$

⸻

六、EM算法的本质理解（非常重要）

6.1 从优化角度

👉 EM是在做：

复杂问题 → 转化为“可解子问题”的迭代优化


⸻

6.2 从概率角度

👉 本质：
	•	E步：计算后验
	•	M步：最大化期望

⸻

6.3 从信息论角度

👉 本质：
	•	最大化似然
	•	最小化KL散度

⸻

七、与K-means的关系（高频考点）

👉 结论：

K-means = GMM（协方差固定 + 硬分配）的特例

区别：

方法	分配方式
K-means	硬分配
GMM	概率分配


⸻

八、完整示例（理解关键）

示例：客户分群

目标：
	•	将用户分为K类

方法：
	•	使用GMM
	•	EM算法训练

输出：
	•	每个用户属于每类的概率

⸻

九、常见误区（重点）

❌ 误区1：EM一定收敛到最优

👉 实际：
	•	只保证局部最优

⸻

❌ 误区2：隐变量一定真实存在

👉 实际：
	•	只是建模工具

⸻

❌ 误区3：GMM就是聚类

👉 实际：
	•	是概率生成模型
