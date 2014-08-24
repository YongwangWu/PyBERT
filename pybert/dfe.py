#! /usr/bin/env python

"""
Behavioral model of a decision feedback equalizer (DFE).

Original Author: David Banas <capn.freako@gmail.com>
Original Date:   17 June 2014

This Python script provides a behavioral model of a decision feedback
equalizer (DFE). The class defined, here, is intended for integration
into the larger `PyBERT' framework, but is also capable of
running in stand-alone mode for preliminary debugging, via the
`dfe_demo.py' script.

Copyright (c) 2014 by David Banas; All rights reserved World wide.
"""

from numpy import zeros, sign, array
from cdr   import CDR

class DFE(object):
    """Behavioral model of a decision feedback equalizer (DFE)."""

    def __init__(self, n_taps, gain, delta_t, alpha, ui, decision_scaler,
                       n_ave=10, n_lock_ave=500, rel_lock_tol=0.01, lock_sustain=500):
        """
        Inputs:

          Required:

          - n_taps           # of taps in adaptive filter

          - gain             adaptive filter tap weight correction gain

          - delta_t          CDR proportional branch constant (ps)

          - alpha            CDR integral branch constant (normalized to delta_t)

          - ui               nominal unit interval (ps)

          - decision_scaler  multiplicative constant applied to the result of
                             the sign function, when making a "1 vs. 0" decision.
                             Sets the target magnitude for the DFE.

          Optional:

          - n_ave            The number of averages to take, before adapting.
                             (Also, the number of CDR adjustments per DFE adaptation.)

          - n_lock_ave       The number of unit interval estimates to
                             consider, when determining locked status.

          - rel_lock_tol     The relative tolerance for determining lock.

          - lock_sustain     Length of the histerysis vector used for
                             lock flagging.
        """

        self.tap_weights       = [0.0] * n_taps
        self.tap_values        = [0.0] * n_taps
        self.gain              = gain
        self.ui                = ui
        self.decision_scaler   = decision_scaler
        self.cdr               = CDR(delta_t, alpha, ui, n_lock_ave, rel_lock_tol, lock_sustain)
        self.n_ave             = n_ave
        self.corrections       = zeros(n_taps)

    def step(self, decision, error, update):
        """Step the DFE, according to the new decision and error inputs."""

        # Copy class object variables into local function namespace, for efficiency.
        tap_weights = self.tap_weights
        tap_values  = self.tap_values
        gain        = self.gain
        n_ave       = self.n_ave

        # Calculate this step's corrections and add to running total.
        corrections = [old + new for (old, new) in zip(self.corrections,
                                                       [val * error * gain for val in tap_values])]

        # Update the tap weights with the average corrections, if appropriate.
        if(update):
            tap_weights = [weight + correction / n_ave for (weight, correction) in zip(tap_weights, corrections)]
            corrections = zeros(len(corrections)) # Start the averaging process over, again.

        # Step the filter delay chain and generate the new output.
        tap_values  = [decision] + tap_values[:-1]
        filter_out  = sum(array(tap_weights) * array(tap_values))

        # Copy local values back to their respective class object variables.
        self.tap_weights = tap_weights
        self.tap_values  = tap_values
        self.corrections = corrections

        return filter_out

    def run(self, sample_times, signal):
        """Run the DFE on the input signal."""

        ui                = self.ui
        decision_scaler   = self.decision_scaler
        n_ave             = self.n_ave

        clk_cntr           = 0
        smpl_cntr          = 0
        filter_out         = 0
        nxt_filter_out     = 0
        last_clock_sample  = 0
        next_boundary_time = 0
        next_clock_time    = ui / 2.
        locked             = False

        res         = []
        tap_weights = [self.tap_weights]
        ui_ests     = []
        lockeds     = []
        clocks      = zeros(len(sample_times))
        for (t, x) in zip(sample_times, signal):
            sum_out = x - filter_out
            res.append(sum_out)
            if(t >= next_boundary_time):
                boundary_sample = sum_out
                filter_out = nxt_filter_out
                next_boundary_time += ui
            if(t >= next_clock_time):
                clk_cntr += 1
                clocks[smpl_cntr] = 1
                current_clock_sample = sum_out
                ui, locked = self.cdr.adapt([last_clock_sample, boundary_sample, current_clock_sample])
                decision = sign(x)
                error = sum_out - decision * decision_scaler
                update = locked and (clk_cntr % n_ave) == 0
                if(locked): # We only want error accumulation to happen, when we're locked.
                    nxt_filter_out = self.step(decision, error, update)
                else:
                    nxt_filter_out = self.step(decision, 0., update)
                tap_weights.append(self.tap_weights)
                last_clock_sample  = sum_out
                next_boundary_time = next_clock_time + ui / 2.
                next_clock_time    = next_clock_time + ui
            ui_ests.append(ui)
            lockeds.append(locked)
            smpl_cntr += 1

        self.ui                = ui               

        return (res, tap_weights, ui_ests, clocks, lockeds)
