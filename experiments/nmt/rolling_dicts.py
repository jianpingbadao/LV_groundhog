#!/usr/bin/env python

import argparse
import cPickle
import logging
import pprint
import shelve

import numpy

from groundhog.trainer.SGD_adadelta import SGD as SGD_adadelta
from groundhog.trainer.SGD import SGD as SGD
from groundhog.trainer.SGD_momentum import SGD as SGD_momentum
from groundhog.mainLoop import MainLoop
from experiments.nmt import\
        RNNEncoderDecoder, prototype_search_state, get_batch_iterator
import experiments.nmt

logger = logging.getLogger(__name__)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", help="State to use")
    parser.add_argument("--proto",  default="prototype_search_state",
        help="Prototype state to use for state")
    parser.add_argument("--skip-init", action="store_true",
        help="Skip parameter initilization")
    parser.add_argument("changes",  nargs="*", help="Changes to state", default="")
    return parser.parse_args()

def main():
    args = parse_args()

    state = getattr(experiments.nmt, args.proto)()
    if args.state:
        if args.state.endswith(".py"):
            state.update(eval(open(args.state).read()))
        else:
            with open(args.state) as src:
                state.update(cPickle.load(src))
    for change in args.changes:
        state.update(eval("dict({})".format(change)))

    logging.basicConfig(level=getattr(logging, state['level']), format="%(asctime)s: %(name)s: %(levelname)s: %(message)s")
    logger.debug("State:\n{}".format(pprint.pformat(state)))

    state['rolling_vocab'] = True
    state['use_infinite_loop'] = False
    logger.debug("rolling_vocab set to True, 'use_infinite_loop' set to False")
    rng = numpy.random.RandomState(state['seed'])

    logger.debug("Load data")
    train_data = get_batch_iterator(state, rng)
    train_data.start(-1)

    dx = {}
    dy = {}
    Dx = {}
    Dy = {}
    Cx = {}
    Cy = {}

    for i in xrange(state['n_sym_source']):
        Dx[i] = i
        Cx[i] = i
    for i in xrange(state['n_sym_target']):
        Dy[i] = i
        Cy[i] = i

    def update_dicts(arr, d, D, C, full):
        i_range, j_range = numpy.shape(arr)
        for i in xrange(i_range):
            for j in xrange(j_range):
                word = arr[i,j]
                if word not in d:
                    if len(d) == full:
                        return True
                    if word not in D: # Also not in C
                        key, value = C.popitem()
                        del D[key]
                        d[word] = value
                        D[word] = value
                    else: # Also in C as (d UNION C) is D. (d INTERSECTION C) is the empty set.
                        d[word] = D[word]
                        del C[word]
        return False

    prev_step = 0
    step = 0
    rolling_vocab_dict = {}
    Dx_dict = {}
    Dy_dict = {}

    output = False
    stop = False

    while not stop: # Assumes the shuffling in get_homogeneous_batch_iter is always the same (Is this true?)
        try:
            batch = train_data.next()
            if step == 0:
                rolling_vocab_dict[step] = (batch['x'][:,0].tolist(), batch['y'][:,0].tolist())
        except:
            batch = None
            stop = True

        if batch:
            output = update_dicts(batch['x'], dx, Dx, Cx, state['n_sym_source'])
            output += update_dicts(batch['y'], dy, Dy, Cy, state['n_sym_target'])

            if output:
                Dx_dict[prev_step] = Dx.copy() # Save dictionaries for the batches preceding this one
                Dy_dict[prev_step] = Dy.copy()
                rolling_vocab_dict[step] = (batch['x'][:,0].tolist(), batch['y'][:,0].tolist()) # When we get to this batch, we will need to use a new vocabulary
                # tuple of first sentences of the batch # Uses large vocabulary indices
                prev_step = step
                dx = {}
                dy = {}
                Cx = Dx.copy()
                Cy = Dy.copy()
                output = False
                print step

                update_dicts(batch['x'], dx, Dx, Cx, state['n_sym_source']) # Assumes you cannot fill dx or dy with only 1 batch
                update_dicts(batch['y'], dy, Dy, Cy, state['n_sym_target'])
            
            step += 1

    Dx_dict[prev_step] = Dx.copy()
    Dy_dict[prev_step] = Dy.copy()
    rolling_vocab_dict[step]=0 # Total number of batches # Don't store first sentences here

    with open('rolling_vocab_dict.pkl','w') as f:
        cPickle.dump(rolling_vocab_dict, f)
    Dx_file = shelve.open('Dx_file')
    Dy_file = shelve.open('Dy_file')
    for key in Dx_dict:
        Dx_file[str(key)] = Dx_dict[key]
        Dy_file[str(key)] = Dy_dict[key]
    Dx_file.close()
    Dy_file.close()

if __name__ == "__main__":
    main()