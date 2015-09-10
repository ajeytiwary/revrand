""" Various utilities that help out with things. """

import numpy as np

pairwise = lambda a: zip(a[:-1], a[1:])


def pre_flatten(func):
    def new_func(*args):
        return func(*map(np.atleast_1d, args))
    return new_func

@pre_flatten
def flatten(*args):
    lsts, shapes = zip(*map(lambda x: (x.flatten(), x.shape), args))
    return list(chain(*lsts)), shapes


def unflatten(flat_lst, shapes, order='C'):
    """
    Given a flat (one-dimensional) list, and a list of ndarray shapes return 
    a list of numpy ndarrays of specified shapes.

    Parameters
    ----------
    flat_lst : list
        A flat (one-dimensional) list
    
    shapes : list of tuples
        A list of ndarray shapes (tuple of array dimensions)

    order : {‘C’, ‘F’, ‘A’}, optional
        Reshape array using index order: C (row-major), Fortran (column-major) 
        order, or preserve the C/Fortran ordering from a. The default is ‘C’.
    
    See Also
    --------
    utils.flatten : its inverse

    Notes
    -----
    Roughly equivalent to::

        lambda flat_lst, shapes: [np.asarray(flat_lst[start:end]).reshape(shape) \
            for (start, end), shape in zip(pairwise(np.cumsum([0]+list(map(np.prod, shapes)))), \
                shapes)]

    Examples
    --------
    >>> unflatten([4, 5, 8, 9, 1, 4, 2, 5, 3, 4, 3], [(2,), (3,), (2, 3)])
    [array([4, 5]), array([8, 9, 1]), array([[4, 2, 5], [3, 4, 3]])]
    """

class CatParameters(object):

    def __init__(self, params, log_indices=None):

        self.pshapes = [np.asarray(p).shape if not np.isscalar(p)
                        else 1 for p in params]
        
        if log_indices is not None:
            self.log_indices = log_indices
        else:
            self.log_indices = []

    def flatten(self, params):
        """ This will take a list of parameters of scalars or arrays, and
            return a flattened array which is a concatenation of all of these
            parameters.

            This could be useful for using with an optimiser!

            Arguments:
                params: a list of scalars of arrays.

            Returns:
                list: a list or 1D array of scalars which is a flattened
                    concatenation of params.
        """

        vec = []
        for i, p in enumerate(params):
            fp = np.atleast_1d(p).flatten()
            vec.extend(fp if i not in self.log_indices else np.log(fp))

        return np.array(vec)

    def flatten_grads(self, params, grads):

        vec = []
        for i, (p, g) in enumerate(zip(params, grads)):
            g = np.atleast_1d(g)

            # Chain rule if log params used
            if i in self.log_indices:
                g *= np.atleast_1d(p)

            vec.extend(g.flatten())

        return np.array(vec)

    def unflatten(self, flatparams):
        """ This will turn a flattened list of parameters into the original
            parameter argument list, given a template.

            This could be useful for using after an optimiser!

            Argument:
                params: the template list of parameters.

                flatlist: the flattened list of parameters to turn into the
                    original parameter list.

            Returns:
                list: A list of the same form as params, but with the values
                    from flatlist.
        """

        rparams = []
        listind = 0
        for i, p in enumerate(self.pshapes):
            if np.isscalar(p):
                up = flatparams[listind]
                listind += 1
            else:
                nelems = np.product(p)
                up = np.reshape(flatparams[listind:(listind + nelems)], p)
                listind += nelems

            rparams.append(up if i not in self.log_indices else np.exp(up))

        return rparams


def params_to_list(params):
    """ This will take a list of parameters of scalars or arrays, and return a
        flattened array which is a concatenation of all of these parameters.

        This could be useful for using with an optimiser!

        Arguments:
            params: a list of scalars of arrays.

        Returns:
            list: a list or 1D array of scalars which is a flattened
                concatenation of params.
    """

    vec = []
    for p in params:
        vec.extend(np.atleast_1d(p).flatten())

    return vec


def list_to_params(params, flatlist):
    """ This will turn a flattened list of parameters into the original
        parameter argument list, given a template.

        This could be useful for using after an optimiser!

        Argument:
            params: the template list of parameters.

            flatlist: the flattened list of parameters to turn into the
                original parameter list.

        Returns:
            list: A list of the same form as params, but with the values from
                flatlist.
    """

    rparams = []
    listind = 0
    for p in params:
        if np.isscalar(p):
            rparams.append(flatlist[listind])
            listind += 1
        else:
            p = np.asarray(p)
            nelems = np.product(p.shape)
            rparams.append(np.reshape(flatlist[listind:(listind + nelems)],
                                      p.shape))
            listind += nelems

    return rparams
