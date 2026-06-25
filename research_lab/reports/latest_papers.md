# TradeOps Paper Brief

papers: 16

> Compact markdown generated from paper metadata/abstracts for low-token research review.

## Explainable Patterns in Cryptocurrency Microstructure

- id: `2602.00776v1`
- source: `arxiv`
- score: `25.00`
- published: `2026-01-31T15:33:06Z`
- authors: Bartosz Bieganowski, Robert Ślepaczuk
- keywords: order flow imbalance
- url: http://arxiv.org/abs/2602.00776v1

**Abstract Brief**

We document stable cross-asset patterns in cryptocurrency limit-order-book microstructure: the same engineered order book and trade features exhibit remarkably similar predictive importance and SHAP dependence shapes across assets spanning an order of magnitude in market capitalization (BTC, LTC, ETC, ENJ, ROSE). The data covers Binance Futures perpetual contract order books and trades on 1-second frequency starting from January 1st, 2022 up to October 12th, 2025. Using a unified CatBoost modeling pipeline with a direction-aware GMADL objective and time-series cross validation, we show that feature rankings and partial effects are stable across assets despite heterogeneous liquidity and v...

**Research Use**

Candidate for volatility-regime filters, risk throttles, or high-volatility no-trade gates.

## Beyond the Smile: A Hybrid Convolutional VAE for Crypto Volatility Surfaces

- id: `2606.16961v1`
- source: `arxiv`
- score: `23.00`
- published: `2026-06-15T17:01:00Z`
- authors: Sadanand Singh, Allam Reddy, Manan Chopra
- keywords: volatility
- url: http://arxiv.org/abs/2606.16961v1

**Abstract Brief**

We present a convolutional variational autoencoder for cryptocurrency implied-volatility surfaces, together with a deployable predictor that combines it with a quadratic smile re-fit through a deterministic per-tenor routing rule. Trained on 6,034 fully-filled hourly Binance Options surfaces of BTC and ETH spanning May-October 2023 and parameterised on a common $6 \times 7$ tenor-delta grid, the model attains a hidden-cell surface-completion RMSE in the 0.94-1.56 vol-point range across both markets and mask rates 10-50%. The hybrid predictor attains 0.83 vol points at 50% masking against 7.00 for the smile re-fit alone, an eightfold reduction obtained at no additional inference cost. Unde...

**Research Use**

Candidate for volatility-regime filters, risk throttles, or high-volatility no-trade gates.

## Stochastic Price Dynamics in Response to Order Flow Imbalance: Evidence from CSI 300 Index Futures

- id: `2505.17388v1`
- source: `arxiv`
- score: `22.00`
- published: `2025-05-23T01:53:28Z`
- authors: Chen Hu, Kouxiao Zhang
- keywords: order flow imbalance
- url: http://arxiv.org/abs/2505.17388v1

**Abstract Brief**

We conduct modeling of the price dynamics following order flow imbalance in market microstructure and apply the model to the analysis of Chinese CSI 300 Index Futures. There are three findings. The first is that the order flow imbalance is analogous to a shock to the market. Unlike the common practice of using Hawkes processes, we model the impact of order flow imbalance as an Ornstein-Uhlenbeck process with memory and mean-reverting characteristics driven by a jump-type Lévy process. Motivated by the empirically stable correlation between order flow imbalance and contemporaneous price changes, we propose a modified asset price model where the drift term of canonical geometric Brownian mo...

**Research Use**

Candidate for research review; convert into a testable hypothesis before strategy proposal.

## Returns and Order Flow Imbalances: Intraday Dynamics and Macroeconomic News Effects

- id: `2508.06788v4`
- source: `arxiv`
- score: `22.00`
- published: `2025-08-09T02:34:23Z`
- authors: Makoto Takahashi
- keywords: order flow imbalance
- url: http://arxiv.org/abs/2508.06788v4

**Abstract Brief**

We study the interaction between returns and order flow imbalances in the S&P 500 E-mini futures market using a structural VAR model identified through heteroskedasticity. The model is estimated at one-second frequency for each 15-minute interval, capturing both intraday variation and endogeneity due to time aggregation. We find that macroeconomic news announcements sharply reshape price-flow dynamics: price impact rises, flow impact declines, return volatility spikes, and flow volatility falls. Pooling across days, both price and flow impacts are significant at the one-second horizon, with estimates broadly consistent with stylized limit-order-book predictions. Impulse responses indicate...

**Research Use**

Candidate for volatility-regime filters, risk throttles, or high-volatility no-trade gates.

## Dynamic Grid Trading Strategy: From Zero Expectation to Market Outperformance

- id: `2506.11921v1`
- source: `arxiv`
- score: `20.00`
- published: `2025-06-13T16:11:44Z`
- authors: Kai-Yuan Chen, Kai-Hsin Chen, Jyh-Shing Roger Jang
- keywords: dynamic grid trading
- url: http://arxiv.org/abs/2506.11921v1

**Abstract Brief**

We propose a profitable trading strategy for the cryptocurrency market based on grid trading. Starting with an analysis of the expected value of the traditional grid strategy, we show that under simple assumptions, its expected return is essentially zero. We then introduce a novel Dynamic Grid-based Trading (DGT) strategy that adapts to market conditions by dynamically resetting grid positions. Our backtesting results using minute-level data from Bitcoin and Ethereum between January 2021 and July 2024 demonstrate that the DGT strategy significantly outperforms both the traditional grid and buy-and-hold strategies in terms of internal rate of return and risk control.

**Research Use**

Candidate for research review; convert into a testable hypothesis before strategy proposal.

## Early Detection of Latent Microstructure Regimes in Limit Order Books

- id: `2604.20949v1`
- source: `arxiv`
- score: `20.00`
- published: `2026-04-22T17:47:52Z`
- authors: Prakul Sunil Hiremath, Vruksha Arun Hiremath
- keywords: order flow imbalance
- url: http://arxiv.org/abs/2604.20949v1

**Abstract Brief**

Limit order books can transition rapidly from stable to stressed conditions, yet standard early-warning signals such as order flow imbalance and short-term volatility are inherently reactive. We formalise this limitation via a three-regime causal data-generating process (stable $\to$ latent build-up $\to$ stress) in which a latent deterioration phase creates a prediction window prior to observable stress. Under mild assumptions on temporal drift and regime persistence, we establish identifiability of the latent build-up regime and derive guarantees for strictly positive expected lead-time and non-trivial probability of early detection. We propose a trigger-based detector combining MAX agg...

**Research Use**

Candidate for volatility-regime filters, risk throttles, or high-volatility no-trade gates.

## The Subtle Interplay between Square-root Impact, Order Imbalance & Volatility: A Unifying Framework

- id: `2506.07711v6`
- source: `arxiv`
- score: `19.00`
- published: `2025-06-09T12:53:25Z`
- authors: Guillaume Maitrier, Jean-Philippe Bouchaud
- keywords: order flow imbalance
- url: http://arxiv.org/abs/2506.07711v6

**Abstract Brief**

In this work, we aim to reconcile several apparently contradictory observations in market microstructure: is the famous "square-root law" of metaorder impact, which decays with time, compatible with the random-walk nature of prices and the linear impact of order imbalances? Can one entirely explain the volatility of prices as resulting from the flow of uninformed metaorders that mechanically impact them? We introduce a new theoretical framework to describe metaorders with different signs, sizes and durations, which all impact prices as a square-root of volume but with a subsequent time decay. We show that, as in the original propagator model, price diffusion is ensured by the long memory...

**Research Use**

Candidate for volatility-regime filters, risk throttles, or high-volatility no-trade gates.

## Binary Tree Option Pricing Under Market Microstructure Effects: A Random Forest Approach

- id: `2507.16701v1`
- source: `arxiv`
- score: `19.00`
- published: `2025-07-22T15:37:08Z`
- authors: Akash Deep, Chris Monico, W. Brent Lindquist, Svetlozar T. Rachev, et al.
- keywords: order flow imbalance
- url: http://arxiv.org/abs/2507.16701v1

**Abstract Brief**

We propose a machine learning-based extension of the classical binomial option pricing model that incorporates key market microstructure effects. Traditional models assume frictionless markets, overlooking empirical features such as bid-ask spreads, discrete price movements, and serial return correlations. Our framework augments the binomial tree with path-dependent transition probabilities estimated via Random Forest classifiers trained on high-frequency market data. This approach preserves no-arbitrage conditions while embedding real-world trading dynamics into the pricing model. Using 46,655 minute-level observations of SPY from January to June 2025, we achieve an AUC of 88.25% in fore...

**Research Use**

Candidate for research review; convert into a testable hypothesis before strategy proposal.

## Trading in the Sunshine or in the Shade: Market Impact and Adverse Selection on Hyperliquid

- id: `2606.15715v1`
- source: `arxiv`
- score: `18.00`
- published: `2026-06-14T10:07:34Z`
- authors: Davide Barone, Fabrizio Lillo
- keywords: trading
- url: http://arxiv.org/abs/2606.15715v1

**Abstract Brief**

Sunshine trading theory predicts that publicly disclosing trading intentions can reduce adverse selection and attract liquidity provision, lowering execution costs. Evidence is scarce, because explicit preannouncement of large orders is rare in traditional markets. We study Hyperliquid, a fully on-chain limit order book for cryptocurrency perpetual futures, where protocol-native TWAP orders disclose their terms from inception and remain visible while active, a natural form of sunshine trading. Using address-level data, we reconstruct 4.3 million hidden metaorders and compare them with 465,000 visible TWAP executions. The two execution styles differ sharply: hidden metaorders follow front-...

**Research Use**

Candidate for order-flow, liquidity, slippage, and execution-quality filters.

## Trends, Volatility, Correlations, and Critical Phenomena in Financial Markets

- id: `2606.20145v1`
- source: `arxiv`
- score: `15.00`
- published: `2026-06-18T12:07:48Z`
- authors: Sara A. Safari, Christoph Schmidhuber
- keywords: volatility
- url: http://arxiv.org/abs/2606.20145v1

**Abstract Brief**

We forecast future volatilities and correlations of financial markets based on the current trends in these markets. This complements previous work that models future expected returns by a cubic polynomial of the current trend strength. Empirically, we observe that volatilities and correlations tend to increase day after day in times of strong up- or down-trends. This effect is particularly pronounced in down-trends. It can be accurately quantified by quadratic polynomials of today's trend strengths, which refine common mean-reversion models of volatilities and correlations. Our results improve the prediction of market risk by accounting for market trends. They also support a recent propos...

**Research Use**

Candidate for volatility-regime filters, risk throttles, or high-volatility no-trade gates.

## Fitting Accumulated Stock Returns with Tempered Skew t-Distribution

- id: `2606.19318v1`
- source: `arxiv`
- score: `13.00`
- published: `2026-06-17T17:44:35Z`
- authors: Siqi Shao, R. A. Serota
- keywords: volatility
- url: http://arxiv.org/abs/2606.19318v1

**Abstract Brief**

We analyze distributions of historic S&P500 multi-day returns, for the number of days of accumulation from 20 to 120. With the increase of the number of days of accumulation, we observe clear tempering of power-law tails toward a seemingly finite value. To explain this phenomenon, we employ a model that produces a "capped Inverse Gamma" stationary (steady-state) distribution for stochastic volatility which, in turn, produces a "tempered Student-t" distribution for returns. We then employ Jones-Faddy-like symmetry breaking mechanism that produces a "tempered Skew-t" distribution. This distribution provides rather good fits to the distributions of accumulated multi-day S&P500 returns, which...

**Research Use**

Candidate for volatility-regime filters, risk throttles, or high-volatility no-trade gates.

## How to spot outliers: an Ensemble Anomaly Detection Framework

- id: `2606.20079v1`
- source: `arxiv`
- score: `13.00`
- published: `2026-06-18T10:54:18Z`
- authors: Daniil Peysakhovich, Rafał Sieradzki
- keywords: trading
- url: http://arxiv.org/abs/2606.20079v1

**Abstract Brief**

Errors in risk valuation outputs arising from data-feed failures, model misconfiguration, or system malfunctions can propagate undetected through an investment bank's risk infrastructure and generate material operational losses. Using proprietary daily credit-derivatives data from a major global investment bank covering 183 trades across 129 trading days, we design, implement, and empirically evaluate the Ensemble Quality Assessment Framework (EQAF), a layered unsupervised architecture that combines complementary outlier-detection methods to monitor risk calculation integrity in real time. Using a controlled anomaly-injection protocol with eight operationally realistic scenarios, we show...

**Research Use**

Candidate for research review; convert into a testable hypothesis before strategy proposal.

## DiffLOB: Diffusion Models for Counterfactual Generation in Limit Order Books

- id: `2602.03776v1`
- source: `arxiv`
- score: `8.00`
- published: `2026-02-03T17:34:56Z`
- authors: Zhuohan Wang, Carmine Ventre
- keywords: crypto mean reversion, volatility regime trading, dynamic grid trading, order flow imbalance, market microstructure crypto, walk forward optimization trading, breakout trading volatility filter
- url: http://arxiv.org/abs/2602.03776v1

**Abstract Brief**

Modern generative models for limit order books (LOBs) can reproduce realistic market dynamics, but remain fundamentally passive: they either model what typically happens without accounting for hypothetical future market conditions, or they require interaction with another agent to explore alternative outcomes. This limits their usefulness for stress testing, scenario analysis, and decision-making. We propose \textbf{DiffLOB}, a regime-conditioned \textbf{Diff}usion model for controllable and counterfactual generation of \textbf{LOB} trajectories. DiffLOB explicitly conditions the generative process on future market regimes--including trend, volatility, liquidity, and order-flow imbalance,...

**Research Use**

Candidate for volatility-regime filters, risk throttles, or high-volatility no-trade gates.

## Do Prediction Markets Match Option Prices? Bitcoin Threshold Evidence from Binance and Polymarket

- id: `2606.19517v1`
- source: `arxiv`
- score: `5.00`
- published: `2026-06-17T19:06:52Z`
- authors: Victoria Portnaya
- keywords: mean reversion, volatility, trading, market microstructure
- url: http://arxiv.org/abs/2606.19517v1

**Abstract Brief**

The digitization of financial markets has produced two classes of platforms that price, in principle, the same state - contingent payoffs: centralized crypto-option exchanges and blockchain-based prediction markets. This paper provides the first option-implied benchmark test of prediction-market pricing for cryptocurrency threshold contracts. For each hour in a matched sample, we compare the Polymarket Yes price with the discounted risk-neutral binary value implied by a listed Binance call option on the same underlying, strike, and maturity, and study the gap between them. In the main September 2023 Bitcoin contract, the mean pricing gap equals 5.6 percentage points across 214 hourly obse...

**Research Use**

Candidate for research review; convert into a testable hypothesis before strategy proposal.

## Correlation emergence and the Epps effect in two coupled limit order books

- id: `2606.14182v1`
- source: `arxiv`
- score: `4.00`
- published: `2026-06-12T07:02:39Z`
- authors: Chris Angstmann, Tim Gebbie
- keywords: mean reversion, volatility, trading, market microstructure
- url: http://arxiv.org/abs/2606.14182v1

**Abstract Brief**

We give a unified analytic account of correlation emergence and the Epps effect in two coupled limit order books. The model starts from a discrete random-walk description of order flow with creation, cancellation and diffusion. A pair-trader coupling between the books is introduced at the level of order creation. We clarify how the discrete model reduces to coupled reaction--diffusion equations with a moving reaction boundary defining the transaction price. Using a regularised local-response representation of the coupling, we derive approximate closed-form expressions for realised correlations as a function of aggregation time. Here the Epps effect is shown to arise from three distinct me...

**Research Use**

Candidate for order-flow, liquidity, slippage, and execution-quality filters.

## Revisiting Trade-sign Long-memory and Square-root Law price impact

- id: `2606.16269v1`
- source: `arxiv`
- score: `2.00`
- published: `2026-06-15T06:18:42Z`
- authors: Chris Angstmann, Tim Gebbie
- keywords: mean reversion, volatility, trading, market microstructure
- url: http://arxiv.org/abs/2606.16269v1

**Abstract Brief**

Starting with a coupled discrete reaction--diffusion formulation for the lit and latent order books with non-uniformly sampled event times and meta-order source terms we show how two familiar market-microstructure regularities can emerge from this framework: the long-memory of trade signs associated with the Lillo--Mike--Farmer (LMF) theory and the square-root law (SQRL) of meta-order impact. This uses the well known locally linear order book and constant participation-rate execution in the front dynamics to reduce the dynamics to a Volterra equation whose leading-order solution then yields the well know result of concave impact trajectory, and a completion impact proportional to the squa...

**Research Use**

Candidate for order-flow, liquidity, slippage, and execution-quality filters.
