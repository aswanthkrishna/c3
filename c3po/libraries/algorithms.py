from scipy.optimize import minimize as minimize
import cma.evolution_strategy as cma
import numpy as np
# from nevergrad.optimization import registry as algo_registry


def single_eval(x0, goal_fun, options={}):
    goal_fun(x0)


def lbfgs(x0, goal_fun, grad_fun, options={}):
    # TODO print from the log not from hear
    options.update({'disp': True})
    return minimize(
        goal_fun,
        x0,
        jac=grad_fun,
        method='L-BFGS-B',
        options=options
    )


def cmaes(x0, goal_fun, options={}):
    if 'noise' in options:
        noise = float(options.pop('noise'))
    else:
        noise = 0

    if 'init_point' in options:
        init_point = bool(options.pop('init_point'))
    else:
        init_point = False

    if 'spread' in options:
        spread = bool(options.pop('spread'))
    else:
        spread = 0.1
    settings = options

    es = cma.CMAEvolutionStrategy(x0, spread, settings)
    iter = 0
    while not es.stop():
        samples = es.ask()
        if init_point and iter == 0:
            samples.insert(0,x0)
            print('C3:STATUS:Adding initial point to CMA sample.')
        solutions = []
        for sample in samples:
            goal = goal_fun(sample)
            if noise:
                goal = goal + (np.random.randn() * noise)
            solutions.append(goal)
        es.tell(samples, solutions)
        es.disp()
        iter += 1
    return es


def cma_pre_lbfgs(x0, goal_fun, grad_fun, options={}):
    cma_opts = {'ftarget' : 1e-1}
    es = cmaes(x0, goal_fun, options=cma_opts)
    x1 = es.result.xbest
    lbfgs(x1, goal_fun, grad_fun, options=options)

# def oneplusone(x0, goal_fun):
#     optimizer = algo_registry['OnePlusOne'](instrumentation=x0.shape[0])
#     while True:
#         # TODO make this logging happen elsewhere
#         # self.logfile.write(f"Batch {self.evaluation}\n")
#         # self.logfile.flush()
#         tmp = optimizer.ask()
#         samples = tmp.args
#         solutions = []
#         for sample in samples:
#             goal = goal_fun(sample)
#             solutions.append(goal)
#         optimizer.tell(tmp, solutions)
#
#     # TODO deal with storing best value elsewhere
#     # recommendation = optimizer.provide_recommendation()
#     # return recommendation.args[0]
