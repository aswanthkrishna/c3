"""
Synthetic C3 model learning

Construct two models, a 'wrong' one and a 'correct' one. First construct
open loop pulses with the wrong model then calibrate them against the real
model, simulating an experiment. Finally try to match the wrong model to the
calibration data and recover the real one.
"""

import pickle
import numpy as np
import tensorflow as tf
import c3po.hamiltonians as hamiltonians
from c3po.utils import log_setup
from c3po.component import Quantity as Qty
from c3po.simulator import Simulator as Sim
from c3po.experiment import Experiment as Exp
from c3po.tf_utils import tf_abs
from c3po.qt_utils import basis, xy_basis, perfect_gate
from single_qubit import create_chip_model, create_generator, create_gates

# This import registers the 3D projection, but is otherwise unused.
import matplotlib.pyplot as plt
from matplotlib import ticker, cm

from progressbar import ProgressBar, Percentage, Bar, ETA

logdir = log_setup("/tmp/c3logs/")

# System
qubit_freq = Qty(
    value=5.1173e9 * 2 * np.pi,
    min=5e9 * 2 * np.pi,
    max=5.5e9 * 2 * np.pi,
    unit='Hz 2pi'
)
qubit_anhar = Qty(
    value=-315.513734e6 * 2 * np.pi,
    min=-330e6 * 2 * np.pi,
    max=-300e6 * 2 * np.pi,
    unit='Hz 2pi'
)
qubit_lvls = 4
drive_ham = hamiltonians.x_drive
v_hz_conversion = Qty(
    value=1,
    min=0.9,
    max=1.1,
    unit='rad/V'
)

qubit_freq = Qty(
    value=5.12e9 * 2 * np.pi,
    min=5e9 * 2 * np.pi,
    max=5.5e9 * 2 * np.pi,
    unit='Hz 2pi'
)

carrier_freq = Qty(
    value=5.25e9 * 2 * np.pi,
    min=5e9 * 2 * np.pi,
    max=5.5e9 * 2 * np.pi,
    unit='Hz 2pi'
)

freq_offset = Qty(
    value=0e6 * 2 * np.pi,
    min=-250 * 1e6 * 2 * np.pi,
    max=250 * 1e6 * 2 * np.pi,
    unit='Hz 2pi'
)

qubit_lvls = 4
drive_ham = hamiltonians.x_drive

t_final = Qty(
    value=10e-9,
    min=5e-9,
    max=15e-9,
    unit='s'
)
rise_time = Qty(
    value=0.1e-9,
    min=0.0e-9,
    max=0.2e-9,
    unit='s'
)

# Define the ground state
qubit_g = np.zeros([qubit_lvls, 1])
qubit_g[0] = 1
ket_0 = tf.constant(qubit_g, tf.complex128)
bra_0 = tf.constant(qubit_g.T, tf.complex128)

# Simulation variables
sim_res = 60e9
awg_res = 1.2e9

# Create system
model = create_chip_model(
    qubit_freq, qubit_anhar, qubit_lvls, drive_ham
)
gen = create_generator(
    sim_res, awg_res, v_hz_conversion, logdir=logdir,
    rise_time=rise_time
)
gates = create_gates(
    t_final=t_final,
    v_hz_conversion=v_hz_conversion,
    qubit_freq=qubit_freq,
    qubit_anhar=qubit_anhar,
    freq_offset=freq_offset,
    carrier_freq=carrier_freq
)

# gen.devices['awg'].options = 'drag'

# Simulation class and fidelity function
exp = Exp(
    model,
    gen
)
sim = Sim(exp, gates)
sim.use_VZ = True
a_q = model.ann_opers[0]

# Define states
# Define states & unitaries
ket_0 = tf.constant(basis(qubit_lvls, 0), dtype=tf.complex128)
bra_2 = tf.constant(basis(qubit_lvls, 2).T, dtype=tf.complex128)
bra_yp = tf.constant(xy_basis(qubit_lvls, 'yp').T, dtype=tf.complex128)
X90p = tf.constant(perfect_gate(qubit_lvls, 'X90p'), dtype=tf.complex128)


# TODO move fidelity experiments elsewhere
def state_transfer_infid(U_dict: dict):
    U = U_dict['X90p']
    ket_actual = tf.matmul(U, ket_0)
    overlap = tf_abs(tf.matmul(bra_yp, ket_actual))
    infid = 1 - overlap
    return infid


def unitary_infid(U_dict: dict):
    U = U_dict['X90p']
    unit_fid = tf_abs(
        tf.linalg.trace(tf.matmul(U, tf.linalg.adjoint(X90p))) / 2
    )**2
    infid = 1 - unit_fid
    return infid


def pop_leak(U_dict: dict):
    U = U_dict['X90p']
    ket_actual = tf.matmul(U, ket_0)
    overlap = tf_abs(tf.matmul(bra_2, ket_actual))
    return overlap


def match_calib(
    exp_params: list,
    exp_opt_map: list,
    gateset_values: list,
    gateset_opt_map: list,
    seq: list,
    fid: np.float64
):
    exp.set_parameters(exp_params, exp_opt_map)
    sim.gateset.set_parameters(gateset_values, gateset_opt_map)
    U_dict = sim.get_gates()
    fid_sim = unitary_infid(U_dict)
    diff = fid_sim - fid
    return diff


def infid_sim(qubit_freq, drive_freq):
    exp.set_parameters(qubit_freq, exp_opt_map)
    sim.gateset.set_parameters(drive_freq, opt_map, scaled=True)
    U_dict = sim.get_gates()
    return unitary_infid(U_dict)


# Optimizer object
opt_map = [
    # [('X90p', 'd1', 'gauss', 'amp')],
    [('X90p', 'd1', 'gauss', 'freq_offset')],
    # [('X90p', 'd1', 'gauss', 'xy_angle')],
    # # [('X90p', 'd1', 'gauss', 'delta')]
]

exp_opt_map = [
    ('Q1', 'freq'),
    # ('Q1', 'anhar'),
    # ('Q1', 't1'),
    # ('Q1', 't2star'),
    # ('v_to_hz', 'V_to_Hz'),
    # ('resp', 'rise_time')
]


# Make data.
def gen_data(step):
    with tf.device('/CPU:0'):
        X = np.arange(-1, 1, step)
        Y = np.arange(-1, 1, step)
        infid = np.zeros((X.shape[0], Y.shape[0]))
        widgets = [
            'Sweep: ',
            Percentage(),
            ' ',
            Bar(marker='=', left='[', right=']'),
            ' ',
            ETA()
        ]
        pbar = ProgressBar(widgets=widgets, maxval=X.shape[0])
        pbar.start()
        ii = 0
        for val in pbar(range(X.shape[0])):
            for jj in range(Y.shape[0]):
                infid[ii][jj] = infid_sim([X[ii]], [Y[jj]])
            pbar.update(ii)
            ii += 1
        pbar.finish()
        X, Y = np.meshgrid(X, Y)
        return X, Y, infid


def read_data():
    X = np.arange(-1, 1, 0.1)
    Y = np.arange(-1, 1, 0.1)
    X, Y = np.meshgrid(X, Y)
    with open("2d_scan.pickle", 'rb') as file:
        infid = pickle.load(file)
    return X, Y, infid


def plot(data):
    X, Y, infid = data
    fig = plt.figure()
    ax = fig.gca()
    cs = ax.contourf(
        qubit_freq.get_value(X)/2e9/np.pi,
        (carrier_freq.get_value() + freq_offset.get_value(Y))/2e9/np.pi,
        infid
    )
    cbar = fig.colorbar(cs)
    cbar.set_label('Unitary infidelity')
    ax.xaxis.set_label_text("Qubit freq [GHz 2pi]")
    ax.yaxis.set_label_text('Drive freq [GHz 2pi]')
    plt.grid()
    plt.show()