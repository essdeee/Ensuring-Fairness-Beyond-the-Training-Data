import cvxpy as cp 
import numpy as np
import math
import time 
import itertools
import pickle
from bayesian_oracle import BayesianOracle
from voting_classifier import VotingClassifier

""" The Meta-Algorithm (Algorithm 1) that performs gradient descent on the weights and  
calls the Bayesian oracle at each time step t. The main function here is meta_algorithm().

:param T: the number of steps to run the Meta-Algo
:type int

:param T_inner: the number of steps to run the Bayesian Oracle
:type int:

:param card_A: the cardinality of A, the set of protected attributes
:type int:

:param M: the bound on the loss
:type float:

:param epsilon: the desired "fairness gap" between the protected attributes
:type float:

:param num_cores: the number of cores to use for multiprocessing in LPs
:type int:

:param solver: the LP solver designated
:type str:

:param B: the bound on each Lambda 
:type float:

:param eta: the learning/gradient descent rate for the weights in Meta-Algo
:type float:

:param gamma_1: a parameter that sets how many "buckets" to discretize the weight 
vectors in the Bayesian Oracle and Lambda Best Response step.
:type float:

:param gamma_2: a parameter that sets how many "buckets" to discretize the weight 
vectors pi in the Lambda Best Response step.
:type float:
"""

class MetaAlgorithm:
    def __init__(self, T, T_inner, eta, eta_inner, card_A = 2, epsilon = 0.05, num_cores = 2, solver = 'ECOS',
                B = 0.1, gamma_1 = 0.001, gamma_2 = 0.05, fair_constraint='eo', gp_wt_bd=0.1, prev_h_t = None, 
                prev_w_t = None, only_h0=False):
        self.T = T
        self.T_inner = T_inner
        self.card_A = card_A
        self.B = B
        self.eta = eta
        self.eta_inner = eta_inner
        self.gamma_1 = gamma_1
        self.gamma_2 = gamma_2
        self.epsilon = epsilon
        self.num_cores = num_cores
        self.solver = solver
        self.fair_constraint = fair_constraint
        self.gp_wt_bd = gp_wt_bd
        self.prev_h_t = prev_h_t
        self.prev_w_t = prev_w_t
        self.only_h0 = only_h0

        if(self.epsilon - 4 * self.gamma_1 < 0):
            raise(ValueError("epsilon - 4 * gamma_1 must be positive for LPs."))
        if(self.fair_constraint not in ['dp', 'eo']):
            raise(ValueError("Fairness constraint must be either dp or eo."))
        if eta is None:
            self.eta = 1/np.sqrt(2*self.T)
        if self.prev_h_t == None and self.prev_w_t != None:
            raise(ValueError("prev_w_t and prev_h_t must be both specified/unspecified."))
        if self.prev_h_t != None and self.prev_w_t == None:
            raise(ValueError("prev_w_t and prev_h_t must be both specified/unspecified."))
        
        print("=== HYPERPARAMETERS ===")
        print("T=" + str(self.T))
        print("T_inner=" + str(self.T_inner))
        print("B=" + str(self.B))
        print("gamma_1=" + str(self.gamma_1))
        print("gamma_2=" + str(self.gamma_2))
        print("eta=" + str(self.eta))
        print("eta_inner=" + str(self.eta_inner))
        print("epsilon=" + str(self.epsilon))
        print("gp_wt_bd=" + str(self.gp_wt_bd))
        print("Cores in use=" + str(self.num_cores))
        print("Fairness Definition=" + str(self.fair_constraint))
        print("onlyh0=" + str(self.only_h0))

    def _gamma_1_buckets(self, X):
        """
        Returns the discretized buckets for each weight vector in N(gamma_1, W).

        :return: list 'gamma_1_buckets' of 2-tuples for the range of each bucket.
        """
        delta_1 = self.gamma_1 / (2 * len(X))

        gamma_1_num_buckets = int(np.ceil(math.log((1/delta_1), 1 + self.gamma_1)))
        gamma_1_buckets = []
        gamma_1_buckets.append((0, delta_1))
        for i in range(gamma_1_num_buckets):
            bucket_lower = ((1 + self.gamma_1) ** i) * (delta_1)
            bucket_upper = ((1 + self.gamma_1) ** (i + 1)) * (delta_1)
            gamma_1_buckets.append((bucket_lower, bucket_upper))
        
        print("First 5 entries of N_gamma_1:")
        print(gamma_1_buckets[:4])
        print("Number of gamma_1_buckets {}".format(len(gamma_1_buckets)))
                            
        return gamma_1_buckets

    def _gamma_2_buckets(self, y, proportions):
        """
        Returns the pi_a0 and pi_a1 for the LPs, N(gamma_2, A). Number of LPs
        depends on this.

        :return: dict 'N_gamma_2_A' of lists, indexed by 'dp,' 'eo_y0,' and 'eo_y1.' 
        each value in this dict is a list of pi_a0 and pi_a1 tuples.
        """
        N_gamma_2_A = {}
        delta_2 = 0.05 

        ### Demographic Parity (dp) buckets ###
        dp_gamma_2_num_buckets = np.ceil(math.log((1/delta_2), 1 + self.gamma_2)) 
        dp_gamma_2_buckets = []
        for j in range(int(dp_gamma_2_num_buckets)):
            bucket = (delta_2) * (1 + self.gamma_2)**j
            dp_gamma_2_buckets.append(bucket)

        dp_N_gamma_2_A  = []
        for pi_a in dp_gamma_2_buckets:
            pi_ap = 1 - pi_a
            if(proportions['a0'] - self.gp_wt_bd <= pi_a and pi_a <= proportions['a0'] + self.gp_wt_bd 
            and proportions['a1'] - self.gp_wt_bd <= pi_ap and pi_ap <= proportions['a1'] + self.gp_wt_bd):
                assert(pi_ap + pi_a == 1)
                dp_N_gamma_2_A.append((pi_a, pi_ap))

        N_gamma_2_A['dp'] = dp_N_gamma_2_A

        ### Equalized Odds Buckets ###
        delta_2 = self.gp_wt_bd/2
        pi_00_logterm = (proportions['a0_y0'] + self.gp_wt_bd)/(proportions['a0_y0'] - self.gp_wt_bd + delta_2)
        pi_00_num_buckets = int(np.ceil(math.log(pi_00_logterm, 1 + self.gamma_2)))
        pi_00_buckets = []
        pi_00_buckets.append(proportions['a0_y0'] - self.gp_wt_bd)
        for j in range(pi_00_num_buckets):
            bucket = (proportions['a0_y0'] - self.gp_wt_bd + delta_2) * (1 + self.gamma_2)**j
            pi_00_buckets.append(bucket)

        pi_01_logterm = (proportions['a0_y1'] + self.gp_wt_bd)/(proportions['a0_y1'] - self.gp_wt_bd + delta_2)
        pi_01_num_buckets = int(np.ceil(math.log(pi_01_logterm, 1 + self.gamma_2)))
        pi_01_buckets = []
        pi_01_buckets.append(proportions['a0_y1'] - self.gp_wt_bd)
        for j in range(pi_01_num_buckets):
            bucket = (proportions['a0_y1'] - self.gp_wt_bd + delta_2) * (1 + self.gamma_2)**j
            pi_01_buckets.append(bucket)

        pi_10_logterm = (proportions['a1_y0'] + self.gp_wt_bd)/(proportions['a1_y0'] - self.gp_wt_bd + delta_2)
        pi_10_num_buckets = int(np.ceil(math.log(pi_10_logterm, 1 + self.gamma_2)))
        pi_10_buckets = []
        pi_10_buckets.append(proportions['a1_y0'] - self.gp_wt_bd)
        for j in range(pi_10_num_buckets):
            bucket = (proportions['a1_y0'] - self.gp_wt_bd + delta_2) * (1 + self.gamma_2)**j
            pi_10_buckets.append(bucket)

        print('pi00{}'.format(pi_00_buckets))
        print('pi01{}'.format(pi_01_buckets))
        print('pi10{}'.format(pi_10_buckets))

        eo_y0_N_gamma_2_A = []
        eo_y1_N_gamma_2_A = []
        eo_N_gamma_2_A = []
        for prod in itertools.product(pi_00_buckets, pi_10_buckets, pi_01_buckets):
            pi_11 = 1 - prod[0] - prod[1] - prod[2]
            if(proportions['a1_y1'] - self.gp_wt_bd <= pi_11 and pi_11 <= proportions['a1_y1'] + self.gp_wt_bd):
                eo_y0_N_gamma_2_A.append((prod[0], prod[1]))
                eo_y1_N_gamma_2_A.append((prod[2], pi_11))

                assert(proportions['a0_y0'] - self.gp_wt_bd <= prod[0] and prod[0] <= proportions['a0_y0'] + self.gp_wt_bd)
                assert(proportions['a1_y0'] - self.gp_wt_bd <= prod[1] and prod[1] <= proportions['a1_y0'] + self.gp_wt_bd)
                assert(proportions['a0_y1'] - self.gp_wt_bd <= prod[2] and prod[2] <= proportions['a0_y1'] + self.gp_wt_bd)
                assert(proportions['a1_y1'] - self.gp_wt_bd <= pi_11 and pi_11 <= proportions['a1_y1'] + self.gp_wt_bd)

                eo_N_gamma_2_A.append((prod[0], prod[1], prod[2], pi_11))

        N_gamma_2_A['eo_y0'] = eo_y0_N_gamma_2_A
        N_gamma_2_A['eo_y1'] = eo_y1_N_gamma_2_A
        N_gamma_2_A['eo'] = eo_N_gamma_2_A

        if(self.fair_constraint == 'dp'):
            print("N(gamma_2, A) constraints:")
            print(N_gamma_2_A['dp'])
        elif(self.fair_constraint == 'eo'):
            print("N(gamma_2, A) constraints for Y = 0:")
            print(N_gamma_2_A['eo_y0'])
            print("N(gamma_2, A) constraints for Y = 1:")
            print(N_gamma_2_A['eo_y1'])
            print("N(gamma_2, A) total consttraints:")
            print(N_gamma_2_A['eo'])
                        
        return N_gamma_2_A

    def _zero_one_loss_grad_w(self, pred, y):
        """
        Returns the zero one loss for each sample (gradient w.r.t. w)

        :return: nparray 'loss_vec' which is zero one loss for each training instance.
        """
        loss_vec = []
        for (i,y_true) in enumerate(y):
            if(y_true == pred[i]):
                loss_vec.append(0)
            else:
                loss_vec.append(1)
                
        return np.asarray(loss_vec)

    def _project_W(self, w, a_indices, y, proportions):
        """
        Project w back onto the feasible set of weights

        :return: nparray 'x.value' which is the projected weight vector.
        """
        x = cp.Variable(len(w))
        objective = cp.Minimize(cp.sum_squares(w - x))
        constraints = [0 <= x, 
                        x <= 1, 
                        cp.sum(x) == 1]  
        
        prob = cp.Problem(objective, constraints)
        prob.solve(solver=self.solver, verbose=False)

        if prob.status in ["infeasible", "unbounded"]:
            raise(cp.SolverError("project_W failed to find feasible solution."))

        return x.value
    
    def _update_w(self, X, y, a_indices, prev_h_t, w, proportions):
        loss_vec = self._zero_one_loss_grad_w(prev_h_t.predict(X), y)
        w_t = w + self.eta * loss_vec 
        w_t = self._project_W(w_t, a_indices, y, proportions)
        return w_t

    def _alternate_update_w(self, X, y, a_indices, inner_hypotheses_t, w, proportions):
        T_inner_sum_loss = np.zeros(len(X))
        for h in inner_hypotheses_t:
            T_inner_sum_loss += self._zero_one_loss_grad_w(h.predict(X), y)
        
        w += self.eta * np.divide(T_inner_sum_loss.astype(float), len(inner_hypotheses_t)) # avg. over the T_inner classifiers
        w = self._project_W(w, a_indices, y, proportions)
        return w

    def _set_a_indices(self, sensitive_features, y):
        """
        Creates a dictionary a_indices that contains the necessary information for which indices
        contain the sensitive/protected attributes.

        :return: dict 'a_indices' which contains a list of the a_0 indices, list of a_1 indices,
        list of a_0 indices where y = 0, list of a_0 indices where y = 1, list of a_1 indices
        where y = 0, list of a_1 indices where y = 1, and a list containing the a value of each sample.
        """
        a_indices = dict()
        a_indices['a0'] = sensitive_features.index[sensitive_features.eq(0)].tolist()
        a_indices['a1'] = sensitive_features.index[sensitive_features.eq(1)].tolist()
        a_indices['all'] = sensitive_features.tolist()

        y0 = set(np.where(y == 0)[0])
        y1 = set(np.where(y == 1)[0])
        a_indices['a0_y0'] = list(y0.intersection(set(a_indices['a0'])))
        a_indices['a0_y1'] = list(y1.intersection(set(a_indices['a0'])))
        a_indices['a1_y0'] = list(y0.intersection(set(a_indices['a1'])))
        a_indices['a1_y1'] = list(y1.intersection(set(a_indices['a1'])))

        assert(len(a_indices['a0']) + len(a_indices['a1']) == len(y))
        assert(len(a_indices['a0_y0']) + len(a_indices['a0_y1']) + len(a_indices['a1_y0']) + len(a_indices['a1_y1']) == len(y))
        return a_indices

    def _set_proportions(self, a_indices, y):
        proportions = {}
        proportions['a0'] = len(a_indices['a0'])/float(len(y))
        proportions['a1'] = len(a_indices['a1'])/float(len(y))
        proportions['a0_y0'] = len(a_indices['a0_y0'])/float(len(y))
        proportions['a0_y1'] = len(a_indices['a0_y1'])/float(len(y))
        proportions['a1_y0'] = len(a_indices['a1_y0'])/float(len(y))
        proportions['a1_y1'] = len(a_indices['a1_y1'])/float(len(y))
        proportions['y0'] = (len(np.where(y == 0)[0]))/float(len(y))
        proportions['y1'] = (len(np.where(y == 1)[0]))/float(len(y))

        print('y0 proportion = {}'.format(proportions['y0']))
        print('y1 proportion = {}'.format(proportions['y1']))
        print('a0 proportion = {}'.format(proportions['a0']))
        print('a1 proportion = {}'.format(proportions['a1']))
        print('a0 y0 proportion = {}'.format(proportions['a0_y0']))
        print('a1 y0 proportion = {}'.format(proportions['a1_y0']))
        print('a0 y1 proportion = {}'.format(proportions['a0_y1']))
        print('a1 y1 proportion = {}'.format(proportions['a1_y1']))
        return proportions

    def meta_algorithm(self, X, y, sensitive_features, X_test, y_test, sensitive_features_test, verbose=True):
        """
        Runs the meta-algorithm, calling the bayesian_oracle at each time step (which itself calls
        the lambda_best_response_param_parallel). Meta-algorithm runs for T steps, and the Bayesian oracle
        runs for T_inner many steps. 
        
        NOTE: X, y, sensitive_features are given as Pandas dataframes here. Also note that
        X_test, y_test are only used to get some statistics on how well each Bayesian oracle 
        step is doing w.r.t. the fairness constraint.

        :return: 
        list 'hypotheses' the actual list of (T_inner * T) hypotheses
        VotingClassifier, an object that takes a majority vote over (T_inner * T) hypotheses
        """
        start_outer = time.time()
        print("Number of examples = {}".format(len(X)))
        a_indices = self._set_a_indices(sensitive_features, y) # dictionary with sensitive value locations
        proportions = self._set_proportions(a_indices, y)      # dictionary with all pi values

        w = np.full((X.shape[0],), 1/X.shape[0]) # each weight starts as uniform 1/n
        gamma_1_buckets = self._gamma_1_buckets(X)
        gamma_2_buckets = self._gamma_2_buckets(y, proportions)
        hypotheses = []

        if(self.prev_h_t == None):
            # Start off with oracle prediction over uniform weights
            print("=== Initializing h_0... ===")
            oracle = BayesianOracle(X, y, X_test, y_test, w, sensitive_features, sensitive_features_test,
                                    a_indices,
                                    self.card_A, 
                                    self.B, 
                                    self.T_inner,
                                    self.gamma_1,
                                    gamma_1_buckets, 
                                    gamma_2_buckets, 
                                    self.epsilon,
                                    self.eta_inner,
                                    self.num_cores,
                                    self.solver,
                                    self.fair_constraint,
                                    0, verbose)
            h_t, inner_hypotheses_t = oracle.execute_oracle() # t = 0
            h_0 = h_t
            hypotheses.append(h_t)
        else:
            # Continue by setting h_t to the previous h_t 
            print("=== CONTINUING from {}... ===".format(self.prev_h_t))
            pickled_h_t = open(self.prev_h_t,"rb")
            h_t = pickle.load(pickled_h_t)
            pickled_w_t = open(self.prev_w_t,"rb")
            w = pickle.load(pickled_w_t)

        if(not self.only_h0):
            print("=== ALGORITHM 1 EXECUTION ===")
            for t in range(self.T):
                start_inner = time.time()
                w = self._update_w(X, y, a_indices, h_t, w, proportions)
                print("Updated w vector={}".format(w[:10]))
                print("Loss vector={}".format(self._zero_one_loss_grad_w(h_t.predict(X), y)[:10]))

                if(self.fair_constraint == 'dp'):
                    print("Updated w vector prop. a0={}".format(np.sum(w[a_indices['a0']])))
                    print("Updated w vector prop. a1={}".format(np.sum(w[a_indices['a1']])))
                elif(self.fair_constraint == 'eo'):
                    print("Updated w vector prop. a0y0={}".format(np.sum(w[a_indices['a0_y0']])))
                    print("Updated w vector prop. a1y0={}".format(np.sum(w[a_indices['a1_y0']])))
                    print("Updated w vector prop. a0y1={}".format(np.sum(w[a_indices['a0_y1']])))
                    print("Updated w vector prop. a1y1={}".format(np.sum(w[a_indices['a1_y1']])))

                #w = self._alternate_update_w(X, y, a_indices, inner_hypotheses_t, w, proportions)
                oracle = BayesianOracle(X, y, X_test, y_test, w, sensitive_features, sensitive_features_test,
                                    a_indices,
                                    self.card_A, 
                                    self.B, 
                                    self.T_inner,
                                    self.gamma_1,
                                    gamma_1_buckets, 
                                    gamma_2_buckets, 
                                    self.epsilon,
                                    self.eta_inner,
                                    self.num_cores,
                                    self.solver,
                                    self.fair_constraint,
                                    t + 1,
                                    verbose) # just to print which outer loop T we're on
                
                h_t, inner_hypotheses_t = oracle.execute_oracle()
                hypotheses.append(h_t) # concatenate all of the inner loop hypotheses 

                end_inner = time.time()
                print("ALGORITHM 1 (Meta Algorithm) Loop " + str(t  + 1) + " Completed!")
                print("ALGORITHM 1 (Meta Algorithm) Time/loop: " + str(end_inner - start_inner))
            
            end_outer = time.time()
            print("ALGORITHM 1 (Meta Algorithm) Total Execution Time: " + str(end_outer - start_outer))
            
        return hypotheses, VotingClassifier(hypotheses), h_t, w, h_0 
