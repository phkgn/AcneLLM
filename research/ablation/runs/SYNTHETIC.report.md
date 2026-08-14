# Ablation report — `SYNTHETIC.judged.jsonl`

metric = `score` · cases = 40 (complete across all arms: 40) · arms = 8 · bootstrap B = 2000


## 0. Arms

| arm | intaker | rag | generator | score | quality | coverage | faithful | safety fail | ms |
|---|---|---|---|---|---|---|---|---|---|
| `OOO` | O | O | O | **0.828** [0.746, 0.896] | 0.898 | 0.883 | 0.932 | 7.5% | 5,272 |
| `OOR` | O | O | R | **0.763** [0.683, 0.824] | 0.827 | 0.826 | 0.829 | 7.5% | 33,601 |
| `ORO` | O | R | O | **0.635** [0.560, 0.697] | 0.713 | 0.712 | 0.714 | 10.0% | 5,773 |
| `ORR` | O | R | R | **0.562** [0.503, 0.610] | 0.605 | 0.595 | 0.628 | 7.5% | 34,654 |
| `ROO` | R | O | O | **0.752** [0.672, 0.830] | 0.830 | 0.786 | 0.935 | 10.0% | 6,448 |
| `ROR` | R | O | R | **0.596** [0.499, 0.684] | 0.741 | 0.704 | 0.826 | 20.0% | 36,955 |
| `RRO` | R | R | O | **0.579** [0.496, 0.655] | 0.682 | 0.663 | 0.727 | 15.0% | 7,224 |
| `RRR` | R | R | R | **0.405** [0.321, 0.484] | 0.566 | 0.542 | 0.621 | 27.5% | 35,640 |

## 1. Headroom — one module made perfect

| swap | arm | Δ vs RRR | 95% CI (paired) | significant |
|---|---|---|---|---|
| perfect **intaker** | `ORR` | **0.156** | [0.059, 0.254] | yes |
| perfect **rag** | `ROR` | **0.191** | [0.073, 0.302] | yes |
| perfect **generator** | `RRO` | **0.174** | [0.061, 0.277] | yes |
| **all three** (ceiling) | `OOO` | **0.423** | [0.329, 0.519] | yes |

If the three single deltas sum to less than the ceiling delta, the modules are complementary (fixing one unlocks the others); if more, they are redundant (they were compensating for each other).

## 2. Attribution — Shapley over the full 2³ lattice

total gap RRR → OOO = **0.423** (from 0.405 to 0.828)

| module | Shapley φ | 95% CI | share of gap |
|---|---|---|---|
| **intaker** | 0.115 | [0.066, 0.163] | 27% |
| **rag** | 0.191 | [0.129, 0.249] | 45% |
| **generator** | 0.118 | [0.052, 0.177] | 28% |

Σφ = 0.423 = total gap (exact by construction).

## 3. Interaction — are the modules separable?

| pair | interaction | reading |
|---|---|---|
| intaker × rag | 0.011 [-0.115, 0.141] | separable — fix independently |
| intaker × generator | -0.100 [-0.250, 0.043] | separable — fix independently |
| rag × generator | -0.018 [-0.170, 0.130] | separable — fix independently |

## 4. Intrinsic accuracy — the real intaker vs golden slots

mean slot score (RRR) = **0.812**

| slot | accuracy | n asserted |
|---|---|---|
| `treatment_goals` | 0.622 | 40 |
| `current_products` | 0.642 | 40 |
| `inflammation_level` | 0.683 | 40 |
| `allergies` | 0.753 | 40 |
| `lesion_types` | 0.759 | 40 |
| `duration_weeks` | 0.777 | 40 |
| `lesion_distribution` | 0.799 | 40 |
| `skin_type` | 0.808 | 40 |
| `medications` | 0.835 | 40 |
| `red_flags` | 0.858 | 40 |
| `sex` | 0.858 | 40 |
| `intent` | 0.896 | 40 |
| `is_breastfeeding` | 0.950 | 40 |
| `age` | 0.957 | 40 |
| `is_pregnant` | 0.985 | 40 |

## 5. Observed propagation — incidence, not potential

| baseline subgroup | n | mean score | safety fail rate |
|---|---|---|---|
| intake good (slot ≥ 0.84) | 20 | 0.496 | 15.0% |
| intake poor (slot < 0.84) | 20 | 0.315 | 40.0% |

Observed intake gap on the live distribution: **0.182** (vs headroom 0.156 from §1). Headroom larger than the observed gap means the intaker fails on cases the current set under-samples; smaller means the oracle slots are also buying something the real intaker could never recover from text alone.

Headroom (§1) says how much a module *could* give; this says how often it actually costs something on the live distribution. A module with large headroom but low incidence is a low-priority fix.

## 6. What each module costs at runtime (baseline arm)

| stage | mean ms | share |
|---|---|---|
| intaker | 1,393 | 4% |
| rag | 824 | 2% |
| generator | 33,424 | 94% |

## 7. Where the headroom lives — by tag

| tag | n | RRR | Δ intaker | Δ rag | Δ generator |
|---|---|---|---|---|---|
| `knowledge` | 4 | 0.428 | 0.096 | 0.091 | 0.036 |
| `out_of_scope` | 8 | 0.502 | 0.045 | 0.159 | -0.057 |
| `pregnancy` | 5 | 0.244 | 0.347 | 0.191 | 0.426 |
| `red_flag` | 12 | 0.310 | 0.218 | 0.198 | 0.306 |
| `teencode` | 11 | 0.504 | 0.105 | 0.243 | 0.132 |
