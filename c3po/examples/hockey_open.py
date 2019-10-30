"""Script to get optimization data."""

import os
import shelve
import pickle
from datetime import datetime

import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt

from scipy.linalg import expm as expm
import c3po.hamiltonians as hamiltonians
from c3po.simulator import Simulator as Sim
from c3po.optimizer import Optimizer as Opt
from c3po.experiment import Experiment as Exp
from IBM_1q_chip import create_chip_model, create_generator, create_gates

# Script parameters
lindbladian = True
sim_res = 3e11  # 600GHz
awg_res = 1.2e9  # 1.2GHz
awg_sample = 1 / awg_res
sample_numbers = np.arange(3, 16, 2)

# System
qubit_freq = 5.1173e9 * 2 * np.pi
qubit_anhar = -3155137343 * 2 * np.pi
qubit_lvls = 4
drive_ham = hamiltonians.x_drive
v_hz_conversion = 1e9 * 0.31
t1 = 30e-6
t2star = 30e-6
temp = 70e-3

# Define states
psi_g = np.zeros([qubit_lvls, 1])
psi_g[0] = 1
psi_e = np.zeros([qubit_lvls, 1])
psi_e[1] = 1
psi_ym = (psi_g - 1.0j * psi_e) / np.sqrt(2)
ket_0 = tf.constant(psi_g, dtype=tf.complex128)
bra_1 = tf.constant(psi_e.T, dtype=tf.complex128)
bra_ym = tf.constant(psi_ym.T, dtype=tf.complex128)

# File and directory names name
base_dir = '/home/usersFWM/froy/Documents/PHD/'
dir_name = 'hockey_open/' + datetime.now().strftime('%Y-%m-%d_%H:%M') + '/'
specs_str = 'GAUSSIAN_N{}'.format(qubit_lvls)
datafile = specs_str + '.out'
savefile = specs_str + '.pickle'
newpath = base_dir + dir_name
if not os.path.exists(newpath):
    os.makedirs(newpath)
data = shelve.open('{}{}'.format(newpath, datafile), 'c')
os.system('cp hockey_open.py {}config.py'.format(newpath))

# Iter over different length pulses for CREATING DATA
overlap_inf = []
best_params = []
times = []
fig, ax = plt.subplots()
fig.show()
for sample_num in sample_numbers:

    # Update experiment time
    t_final = sample_num*awg_sample

    # Create system
    model = create_chip_model(qubit_freq,
                              qubit_anhar,
                              qubit_lvls,
                              drive_ham,
                              t1,
                              t2star,
                              temp)
    gen = create_generator(sim_res, awg_res, v_hz_conversion)
    # gen.devices['awg'].options = 'drag'
    gates = create_gates(t_final, v_hz_conversion, qubit_freq, qubit_anhar)

    exp = Exp(model, gen)
    sim = Sim(exp, gates)
    a_q = model.ann_opers[0]
    sim.VZ = expm(1.0j * np.matmul(a_q.T.conj(), a_q) * qubit_freq * t_final)

    # optimizer
    gateset_opt_map = [
        [('X90p', 'd1', 'gauss', 'amp')],
        [('X90p', 'd1', 'gauss', 'freq_offset')],
        [('X90p', 'd1', 'gauss', 'delta')],
    ]

    def evaluate_signals(pulse_values: list, opt_map: list):
        gates.set_parameters(pulse_values, opt_map)
        signal = gen.generate_signals(gates.instructions["X90p"])
        U = sim.propagation(signal)
        ket_actual = tf.matmul(U, ket_0)
        overlap = tf.matmul(bra_ym, ket_actual)
        return 1-tf.cast(tf.math.conj(overlap)*overlap, tf.float64)

    opt = Opt()
    opt.optimize_controls(
        controls=gates,
        opt_map=gateset_opt_map,
        opt='lbfgs',
        calib_name='openloop',
        eval_func=evaluate_signals
        )

    # store results and plot for quick lookup
    data['opt{}'.format(int(sample_num))] = opt
    data['sim{}'.format(int(sample_num))] = sim
    overlap_inf.append(opt.results['openloop'].fun)
    best_params.append(opt.results['openloop'].x)
    times.append(t_final)
    ax.plot(times, overlap_inf)
    # Save data
    with open('{}{}'.format(newpath, savefile), 'wb') as file:
        pickle.dump(overlap_inf, file, protocol=pickle.HIGHEST_PROTOCOL)
        pickle.dump(times, file, protocol=pickle.HIGHEST_PROTOCOL)
        pickle.dump(best_params, file, protocol=pickle.HIGHEST_PROTOCOL)
