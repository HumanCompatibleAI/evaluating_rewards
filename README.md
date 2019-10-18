[![CircleCI](https://circleci.com/gh/HumanCompatibleAI/evaluating_rewards.svg?style=svg)](https://circleci.com/gh/HumanCompatibleAI/evaluating_rewards)
[![codecov](https://codecov.io/gh/HumanCompatibleAI/evaluating_rewards/branch/master/graph/badge.svg)](https://codecov.io/gh/HumanCompatibleAI/evaluating_rewards)

# Evaluating Rewards

`evaluating_rewards` is a library implementing novel ways to evaluate and
compare reward models. We have two main objectives:

1.  To enable simple and rigorous evaluation of reward modeling methods, by
    evaluating the model directly, and not relying on proxy measures such as
    policy behavior.
2.  As a diagnostic tool to understand the strengths and weaknesses of a reward
    model for a particular environment.

We hope to release a technical report summarizing our method in more detail
shortly.

## Getting Started

### Installation

To install `evaluating_rewards`, clone the repository and run:

```
pip install evaluating_rewards/
```

To install in developer mode so that edits will be immediately available:

```
pip install -e evaluating_rewards/
```

The package is compatible with Python 3.6 and upwards. There is no support for
Python 2.

### Obtaining Reward Models

To use `evaluating_rewards`, you will need to have some reward models to
compare. We provide native support to load reward models output by
[imitation](https://github.com/humancompatibleai/imitation), an open-source
implementation of AIRL and GAIL. It is also simple to add new formats to
`serialize.py`.

### Comparing Reward Models

Please see this [Colab notebook](notebooks/comparison.ipynb) for an example of
comparing reward models in a simple point mass environment. The notebook
includes documentation describing the optimization problem we are solving, and
presents visualizations of the resulting reward models. The code can be directly
applied to other environments and reward models, by changing the configuration
and loading the appropriate models. *NOTE*: make sure you run the notebook from
a virtual environment with `evaluating_rewards` installed, so that it can import
the library.

### Other Information

To validate the method, we also compare randomly generated reward models in two
notebooks: one for [deep reward models](notebooks/random_deep.ipynb) and another
in a simple [tabular case](notebooks/random_tabular.ipynb). This may be useful
to better understand the rationale behind this approach, and could be run in new
environments or with new comparison methods as a regression test.

## Technical Structure

`evaluating_rewards` consists of:

-   the main package, containing:
    +   `rewards.py` and `comparisons.py` defining deep reward models and
        associated comparison methods, and `tabular.py` the equivalent in a
        tabular (finite-state) setting.
    +   `serialize.py`, to load reward models, both from this and other
        projects.
-   `envs`, a sub-package defining some simple environments and associated
    hard-coded reward models and (in some cases) policies.
-   `experiments`, a sub-package defining helper methods supporting experiments
    we have performed.

## License

This library is licensed under the terms of the Apache license. See
[LICENSE](LICENSE) for more information.

DeepMind holds the copyright to all work prior to October 4th, during the
lead author's (Adam Gleave) internship at DeepMind. Subsequent modifications
conducted at UC Berkeley are copyright of the author.
Disclaimer: This is not an officially supported Google or DeepMind product.
