# References

The reading behind the algorithm. Entries are reproduced as supplied.

Most of these are metaheuristic feature-selection and text-clustering papers. Their
*question forms* were borrowed and their *search algorithms* deliberately were not:
those run over thousands of features on thousands of documents, and searching rule
subsets against 29 labelled claims would memorise them. `src/ablation.py` states this
in full, citing Abiodun et al. (2021, sec. 5.v).

## Cited in the code

| Source | Where it is used |
| --- | --- |
| Abiodun et al. (2021), sec. 5.v | `src/ablation.py`, `src/expand_gold.py` — why no subset search was run |
| Abualigah & Khader (2017) | `src/ablation.py`, `src/experiments/rule_evidence.py` — ablation as a question, MAD as an unsupervised fitness |
| Lu et al. (2015) | `src/sensitivity.py` — reporting parameter tables rather than an argmax |
| Mosa (2020), sec. 5.4 | `src/sensitivity.py` — "Effects of parameters" |
| Purushothaman et al. (2020) | `src/ablation.py`, `src/experiments/abstain.py` — wrapper selection; fuzzy membership |
| Gopal & Brunda (2019); Majhi (2019) | `src/experiments/abstain.py` — soft membership instead of hard labels |
| Hicks et al., PMC11404377 | `src/tree.py` cross-checking; `src/evaluate.py` metric definitions (specificity, balanced accuracy, F-beta) |

**Four of those are cited in the code but are not in the list below**: Abualigah &
Khader (2017), Gopal & Brunda (2019), Majhi (2019), and Hicks et al. (PMC11404377).
They still need full entries.

## Full list

- Abiodun, E. O., Alabdulatif, A., Abiodun, O. I., Alawida, M., Alabdulatif, A., & Alkhawaldeh, R. S. (2021). A systematic review of emerging feature selection optimization methods for optimal text classification: The present state and prospective opportunities. *Neural Computing and Applications*, *33*(22), 15091--15118. https://doi.org/10.1007/s00521-021-06406-8
- Abualigah, L., Gandomi, A. H., Elaziz, M. A., Hamad, H. Al, Omari, M., Alshinwan, M., & Khasawneh, A. M. (2021). Advances in meta-heuristic optimization algorithms in big data text clustering. *Electronics*, *10*(2), 101. https://doi.org/10.3390/electronics10020101
- Abualigah, L., Gandomi, A. H., Elaziz, M. A., Hussien, A. G., Khasawneh, A. M., Alshinwan, M., & Houssein, E. H. (2020). Nature-inspired optimization algorithms for text document clustering---A comprehensive analysis. *Algorithms*, *13*(12), 345. https://doi.org/10.3390/a13120345
- *AI for signals - MATLAB & Simulink*. (2024). MathWorks. https://www.mathworks.com/help/signal/ai-for-signals.html
- Amazon Web Services. (n.d.). *What is text analysis? - Text analysis explained - AWS*. Amazon Web Services, Inc. Retrieved September 20, 2026, from https://aws.amazon.com/what-is/text-analysis/
- Hirschfield, R. (2025, May 13). *AI text analysis: Choosing the right tool for business*. Babel Street. Babelstreet.Com. https://www.babelstreet.com/blog/choosing-the-right-ai-text-analysis-tool-for-business
- Logically. (2026). *Logically*. Logically. https://logically.ai/glossary/escalation-modeling
- Lopez, M. M., & Kalita, J. (2017). Deep learning applied to NLP. *arXiv:1703.03091 \[Cs\]*. https://arxiv.org/abs/1703.03091
- Lu, Y., Liang, M., Ye, Z., & Cao, L. (2015a). Improved particle swarm optimization algorithm and its application in text feature selection. *Applied Soft Computing*, *35*, 629--636. https://doi.org/10.1016/j.asoc.2015.07.005
- Lu, Y., Liang, M., Ye, Z., & Cao, L. (2015b). Improved particle swarm optimization algorithm and its application in text feature selection. *Applied Soft Computing*, *35*, 629--636. https://doi.org/10.1016/j.asoc.2015.07.005
- Mosa, M. A. (2020). A novel hybrid particle swarm optimization and gravitational search algorithm for multi-objective optimization of text mining. *Applied Soft Computing*, *90*, 106189. https://doi.org/10.1016/j.asoc.2020.106189
- Papageorgiou, G., Economou, P., & Sotirios Bersimis. (2024). A method for optimizing text preprocessing and text classification using multiple cycles of learning with an application on shipbrokers emails. *Journal of Applied Statistics*, 1--35. https://doi.org/10.1080/02664763.2024.2307535
- Purushothaman, R., Rajagopalan, S.P, & Gopinath, D. (2020). Hybridizing Gray Wolf Optimization (GWO) with Grasshopper Optimization Algorithm (GOA) for text feature selection and clustering. *Applied Soft Computing*, *96*, 106651. https://doi.org/10.1016/j.asoc.2020.106651
- Stryker, C. (2025, May 20). *Text classification*. Ibm.Com. https://www.ibm.com/think/topics/text-classification
- Stryker, C., & Holdsworth, J. (2024, August 11). *What is NLP (natural language processing)?* IBM. https://www.ibm.com/think/topics/natural-language-processing
- Zhou, M., Duan, N., Liu, S., & Shum, H.-Y. (2020). Progress in neural NLP: Modeling, learning, and reasoning. *Engineering*, *6*(3), 275--290. https://doi.org/10.1016/j.eng.2019.12.014
- (2020). Mathworks.Com. https://www.mathworks.com/help/signal/ug/machine-and-deep-learning-classification-using-signal-feature-extraction-objects.html

Two notes on the list as supplied: Lu et al. (2015a) and (2015b) are the same paper
listed twice, and the final MathWorks entry has no author or title.
