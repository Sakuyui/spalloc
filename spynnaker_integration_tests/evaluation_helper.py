
class AbstractOptimizationObjective(object):
    pass

class PerformanceOptimizationObjective(object):
    pass

class SpaceUtilizationOptimizationObjective(object):
    pass

class EnergyUtilizationOptimizationObjective(object):
    pass


class EvaluationHelper(object):
    def __init__(self) -> None:
        self.opt_objectives = []
        self.algorithms = []
        self.solution_representation = []
        self.get_cross_strategy = []
        self.get_mutation_strategy = []

    def get_cost_model(self, objective: AbstractOptimizationObjective):
        pass

    def get_solution_fixing_strategy(self):
        pass

    def eval_in_configuration(self):
        pass

    def begin_evaluation(self):
        for objective in self.opt_objectives:
            for cost_model in self.get_cost_model(objective):
                for alg in self.algorithms:
                    for rep in self.solution_representation:
                        for cross_strategy in self.get_cross_strategy(rep, cost_model, objective):
                            for mutation_strategy in self.get_mutation_strategy(rep, cost_model, objective):
                                for solution_fixing_strategy in self.get_solution_fixing_strategy(rep, cost_model, objective):
                                    self.eval_in_configuration(objective, cost_model, rep, cross_strategy, mutation_strategy, solution_fixing_strategy)

    
        