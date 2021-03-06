"""
    Simple plotting for idealised/generic DEM results

    This file is part of Avaframe.
"""


import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import os
import numpy as np
import configparser


def plotDEM(z, name_ext, cfg, outDir):
    """ Plot DEM with given information on the origin of the DEM """

    cfgTopo = cfg['TOPO']
    cfgDEM = cfg['DEMDATA']

    # input parameters
    dx = float(cfgTopo['dx'])
    x_end = float(cfgTopo['xEnd']) + dx
    y_end = float(cfgTopo['yEnd']) + dx
    xl = float(cfgDEM['xl'])
    yl = float(cfgDEM['yl'])
    dem_name = cfgDEM['dem_name']

    # Set coordinate grid with given origin
    xp = np.arange(xl, xl + x_end, dx)
    yp = np.arange(yl, yl + y_end, dx)
    X, Y = np.meshgrid(xp, yp)

    topoNames = {'IP': 'inclined Plane', 'FP': 'flat plane', 'HS': 'Hockeystick',
                 'HS2': 'Hockeystick smoothed', 'BL': 'bowl', 'HX': 'Helix'}

    ax = plt.axes(projection='3d')
    ax.plot_surface(X, Y, z, cmap=plt.cm.viridis,
                    linewidth=0, antialiased=False)

    ax.set_title('Generated DEM: %s' % (topoNames[name_ext]))
    ax.set_xlabel('along valley distance [m]')
    ax.set_ylabel('across valley distance [m]')
    ax.set_zlabel('surface elevation [m]')

    # Save figure to file
    plt.savefig(os.path.join(outDir, '%s_%s_plot.png' % (dem_name, name_ext)))

    # If flag is set, plot figure
    if cfgDEM.getboolean('showplot'):
        plt.show()


def plotReleasePoints(xv, yv, xyPoints, DEM_type):

    plt.figure()
    plt.plot(xv, np.zeros(len(xv))+yv[0], 'k-')
    plt.plot(xv, np.zeros(len(xv))+yv[-1], 'k-')
    plt.plot(np.zeros(len(yv))+xv[0], yv, 'k-')
    plt.plot(np.zeros(len(yv))+xv[-1], yv, 'k-')
    plt.plot(xyPoints[:, 0], xyPoints[:, 1], 'r*')
    plt.title('Domain and release area of %s - projected' % DEM_type)
    plt.xlabel('along valley [m]')
    plt.ylabel('across valley [m]')

    plt.show()
