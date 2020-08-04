#!/usr/bin/env python
# coding: utf-8
""" Main file for module com2AB - Alpha Beta
"""

import os
import pickle
import logging
import numpy as np
import matplotlib.pyplot as plt
import avaframe.in2Trans.shpConversion as shpConv
import avaframe.in3Utils.ascUtils as IOf

# create local logger
log = logging.getLogger(__name__)


# Local imports


def setEqParameters(smallAva, customParam):
    """Set alpha beta equation parameters to
    - standard (default)
    - small avalanche
    - custom
    TODO: test
    """

    eqParameters = {}

    if smallAva is True:
        log.info('Using small Avalanche Setup')
        eqParameters['k1'] = 0.933
        eqParameters['k2'] = 0.0
        eqParameters['k3'] = 0.0088
        eqParameters['k4'] = -5.02
        eqParameters['SD'] = 2.36

        ParameterSet = "Small avalanches"

    elif customParam:
        log.info('Using custom Avalanche Setup')
        eqParameters['k1'] = customParam['k1']
        eqParameters['k2'] = customParam['k2']
        eqParameters['k3'] = customParam['k3']
        eqParameters['k4'] = customParam['k4']
        eqParameters['SD'] = customParam['SD']

        ParameterSet = "Custom"

    else:
        log.info('Using standard Avalanche Setup')
        eqParameters['k1'] = 1.05
        eqParameters['k2'] = -3130.0
        eqParameters['k3'] = 0.0
        eqParameters['k4'] = -2.38
        eqParameters['SD'] = 1.25

        ParameterSet = "Standard"
    eqParameters['ParameterSet'] = ParameterSet
    return eqParameters


def com2ABMain(header, rasterdata, Avapath, SplitPoint,
               saveOutPath, smallAva, customParam, distance):
    """ Loops on the given Avapath and runs com2AB to compute AlpahBeta model
    Inputs : DEM header and rater (as np array),
            Avapath and Split points .shp file,
            optional output save path,
            avalanche type,
            reamplind lenght for the Avapath
    Outputs : writes raw results to saveOutPath
    """
    NameAva = Avapath['Name']
    StartAva = Avapath['Start']
    LengthAva = Avapath['Length']
    CoordAva = Avapath['Coord']

    CoordSplit = SplitPoint['Coord']
    for i in range(len(NameAva)):
        name = NameAva[i]
        start = StartAva[i]
        end = start + LengthAva[i]
        avapath = CoordAva[:, int(start):int(end)]
        com2AB(header, rasterdata, avapath, CoordSplit, saveOutPath, name,
               smallAva, customParam, distance)


def com2AB(header, rasterdata, avapath, splitPoint, OutPath, name,
           smallAva, customParam, distance):
    """ Computes the AlphaBeta model given an input raster (of the DEM),
    an avalanche path and split points
    Inputs : DEM header and rater (as np array),
            single avapath as np array,
            Split points as np array,
            output save path,
            avalanche type,
            resamplind lenght for the Avapath
    Outputs : writes raw results to OutPath
    """

    abVersion = '4.1'
    log.info('Running Version: %s ', abVersion)
    log.info('Running Alpha Beta model on: %s ', name)
    eqParams = setEqParameters(smallAva, customParam)

    # TODO: make rest work with dict

    # read inputs, ressample ava path
    # make pofile and project split point on path
    AvaProfile, SplitPoint, indSplit = prepareLine(
        header, rasterdata, avapath, splitPoint, distance)

    # Sanity check if first element of AvaProfile[3,:]
    # (i.e z component) is highest:
    # if not, flip all arrays
    indSplit, AvaProfile = checkProfile(indSplit, AvaProfile)

    eqIn = {}
    eqIn['s'] = AvaProfile[3, :]  # curvilinear coordinate (of the x, y path)
    eqIn['x'] = AvaProfile[0, :]  # x coordinate of the path
    eqIn['y'] = AvaProfile[1, :]  # y coordinate of the path
    eqIn['z'] = AvaProfile[2, :]  # z coordinate of the path (projection)
    eqIn['indSplit'] = indSplit  # index of split point

    eqOut = calcAB(eqIn, eqParams)
    savename = name + '_com2AB_eqparam.pickle'
    save_file = os.path.join(OutPath, savename)
    with open(save_file, 'wb') as handle:
        pickle.dump(eqParams, handle, protocol=pickle.HIGHEST_PROTOCOL)
    savename = name + '_com2AB_eqout.pickle'
    save_file = os.path.join(OutPath, savename)
    with open(save_file, 'wb') as handle:
        pickle.dump(eqOut, handle, protocol=pickle.HIGHEST_PROTOCOL)


def projectOnRaster(header, rasterdata, Points):
    """ Projects the points Points on Raster using a bilinear interpolation
    and returns the z coord
    Input :
    Points: list of points (x,y) 2 rows as many columns as Points
    Output:
    PointsZ: list of points (x,y,z) 3 rows as many columns as Points

    TODO: test
    """
    xllcorner = header.xllcorner
    yllcorner = header.yllcorner
    cellsize = header.cellsize
    xcoor = Points[0]
    ycoor = Points[1]
    zcoor = np.array([])
    for i in range(np.shape(xcoor)[0]):
        Lx = (xcoor[i] - xllcorner) / cellsize
        Ly = (ycoor[i] - yllcorner) / cellsize
        Lx0 = int(np.floor(Lx))
        Ly0 = int(np.floor(Ly))
        Lx1 = int(np.floor(Lx)) + 1
        Ly1 = int(np.floor(Ly)) + 1
        dx = Lx - Lx0
        dy = Ly - Ly0
        f11 = rasterdata[Ly0][Lx0]
        f12 = rasterdata[Ly1][Lx0]
        f21 = rasterdata[Ly0][Lx1]
        f22 = rasterdata[Ly1][Lx1]
        # using bilinear interpolation on the cell
        value = f11*(1-dx)*(1-dy) + f21*dx*(1-dy) + f12*(1-dx)*dy + f22*dx*dy
        zcoor = np.append(zcoor, value)

    PointsZ = np.vstack((Points, zcoor))
    return (PointsZ)


def prepareLine(header, rasterdata, avapath, splitPoint, distance):
    """ 1- Resample the avapath line with a max intervall of distance=10m
    between points (projected distance on the horizontal plane).
    2- Make avalanch profile out of the path (affect a z value using the DEM)
    3- Get projected split point on the profil (closest point)

    TODO: test
    """

    xcoor = avapath[0]
    ycoor = avapath[1]
    xcoornew = np.array([xcoor[0]])
    ycoornew = np.array([ycoor[0]])
    s = np.array([0])  # curvilinear coordinate
    # loop on the points of the avapath
    for i in range(np.shape(xcoor)[0] - 1):
        Vx = xcoor[i + 1] - xcoor[i]
        Vy = ycoor[i + 1] - ycoor[i]
        D = np.sqrt(Vx**2 + Vy**2)
        nd = int(np.floor(D / distance) + 1)
        # Resample each segment
        S0 = s[-1]
        for j in range(1, nd + 1):
            xn = j / (nd) * Vx + xcoor[i]
            yn = j / (nd) * Vy + ycoor[i]
            xcoornew = np.append(xcoornew, xn)
            ycoornew = np.append(ycoornew, yn)
            s = np.append(s, S0 + D * j / nd)

    # test = np.transpose(np.array([[header.xllcorner,header.yllcorner],
    # [header.xllcorner+header.cellsize*(header.ncols-1),header.yllcorner],
    # [header.xllcorner,header.yllcorner+header.cellsize*(header.nrows-1)],
    # [header.xllcorner+header.cellsize*(header.ncols-1),header.yllcorner+
    # header.cellsize*(header.nrows-1)]]))
    # Test = ProjectOnRaster(header,rasterdata,test)
    ResampAvaPath = np.vstack((xcoornew, ycoornew))
    AvaProfile = projectOnRaster(header, rasterdata, ResampAvaPath)
    AvaProfile = np.vstack((AvaProfile, s))

    # find split point by computing the distance to the line
    SplitPoint, indSplit = findSplitPoint(AvaProfile, splitPoint,
                                          s, xcoornew, ycoornew)

    return AvaProfile, SplitPoint, indSplit


def findSplitPoint(AvaProfile, splitPoint, s, xcoornew, ycoornew):
    """ find split point by computing the distance between splitpoints and the line
        selects the closest splitpoint (if several were given in input)
    """
    Dist = np.empty((0))
    IndSplit = np.empty((0))
    for i in range(np.shape(splitPoint)[1]):
        dist = np.sqrt((xcoornew - splitPoint[0, i])**2 +
                       (ycoornew - splitPoint[1, i])**2)
        indSplit = np.argmin(dist)
        IndSplit = np.append(IndSplit, indSplit)
        Dist = np.append(Dist, dist[indSplit])

    ind = np.argmin(Dist)
    indSplit = int(IndSplit[ind])
    SplitPoint = AvaProfile[:, indSplit]
    SplitPoint = np.append(SplitPoint, s[indSplit])
    return SplitPoint, indSplit


def readRaster(fname):
    """ Read raster file (.asc)"""

    log.info('Reading DEM : %s', fname)
    header = IOf.readASCheader(fname)
    rasterdata = IOf.readASCdata2numpyArray(fname, header)
    rasterdata[rasterdata == header.noDataValue] = np.NaN
    return [header, np.flipud(rasterdata)]


def readAvaPath(fname, outputName, header):
    """ Read avalanche path from  .shp"""

    log.info('Reading avalanche path : %s ', fname)
    defname = outputName
    Avapath = shpConv.SHP2Array(fname, defname)
    avapath = Avapath['Coord']
    if np.shape(avapath)[0] < 2:
        raise ValueError('Ava path file should contain at least 2 columns')
    for i in range(np.shape(avapath)[1]):
        Lx = int(np.floor((avapath[0, i] - header.xllcorner) /
                          header.cellsize))
        Ly = int(np.floor((avapath[1, i] - header.yllcorner) /
                          header.cellsize))
        if (Ly < 0 or Ly > header.nrows or Lx < 0 or Lx > header.ncols):
            raise ValueError('Avalanche path exceeds DEM extend')
    return Avapath


def readSplitPoint(fname, header):
    """ Read split point path from .shp"""

    log.info('Reading split point : %s ', fname)
    defname = 'SHP'
    SplitPoint = shpConv.SHP2Array(fname, defname)
    splitPoint = SplitPoint['Coord']
    if np.shape(splitPoint)[0] < 2:
        raise ValueError('split point file should contain at least 2 columns')
    for i in range(np.shape(splitPoint)[1]):
        Lx = int(np.floor((splitPoint[0, i] - header.xllcorner) /
                          header.cellsize))
        Ly = int(np.floor((splitPoint[1, i] - header.yllcorner) /
                          header.cellsize))
        if (Ly < 0 or Ly > header.nrows or Lx < 0 or Lx > header.ncols):
            raise ValueError('Split point is not on the DEM')
    return SplitPoint


def checkProfile(indSplit, AvaProfile):
    """ check that the avalanche profiles goes from top to bottom """
    if AvaProfile[2, -1] > AvaProfile[2, 0]:
        log.info('Profile reversed')
        L = AvaProfile[3, -1]
        AvaProfile = np.fliplr(AvaProfile)
        AvaProfile[3, :] = L - AvaProfile[3, :]
        indSplit = np.shape(AvaProfile)[1] - indSplit
        return indSplit, AvaProfile
    else:
        return indSplit, AvaProfile


def calcAB(eqInput, eqParameters):
    """
    Calculate Alpha Beta for data in eqInput according to chosen eqParameters
    """
    log.info("Calculating alpha beta")
    k1 = eqParameters['k1']
    k2 = eqParameters['k2']
    k3 = eqParameters['k3']
    k4 = eqParameters['k4']
    SD = eqParameters['SD']

    s = eqInput['s']
    z = eqInput['z']
    indSplit = eqInput['indSplit']
    eqOutput = eqInput.copy()
    ds = np.abs(s - np.roll(s, 1))
    dz = np.abs(z - np.roll(z, 1))
    ds[0] = 0.0
    dz[0] = 0.0
    angle = np.rad2deg(np.arctan2(dz, ds))
    CuSplit = s[indSplit]
    plt.figure(figsize=(10, 6))
    plt.plot(s, angle)
    # plt.show()
    # TODO SPLIT POINT READING
    # get all values where Angle < 10 but >0
    # get index of first occurance and go one back to get previous value
    # (i.e. last value above 10 deg)
    # tmp = x[(angle < 10.0) & (angle > 0.0) & (x > 450)]
    tmp = np.where((angle < 10.0) & (angle > 0.0) & (s > CuSplit))
    ids_10Point = tmp[0][0] - 1
    # Do a quadtratic fit and get the polynom for 2nd derivative later
    zQuad = np.polyfit(s, z, 2)
    poly = np.poly1d(zQuad)
    # Get H0: max - min for parabola
    H0 = max(poly(s)) - min(poly(s))
    # get beta
    dz_beta = z[0] - z[ids_10Point]
    beta = np.rad2deg(np.arctan2(dz_beta, s[ids_10Point]))
    # get Alpha
    alpha = k1 * beta + k2 * poly.deriv(2)[0] + k3 * H0 + k4

    # get Alpha standard deviations
    SDs = [SD, -1*SD, -2*SD]
    alphaSD = k1 * beta + k2 * poly.deriv(2)[0] + k3 * H0 + k4 + SDs

    eqOutput['CuSplit'] = CuSplit
    eqOutput['ids_10Point'] = ids_10Point
    eqOutput['poly'] = poly
    eqOutput['beta'] = beta
    eqOutput['alpha'] = alpha
    eqOutput['SDs'] = SDs
    eqOutput['alphaSD'] = alphaSD
    return eqOutput
