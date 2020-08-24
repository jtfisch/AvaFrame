import sys
import os
import time
import logging
import glob
import math
import numpy as np
import scipy as sp
import copy
import operator
import matplotlib.pyplot as plt
import matplotlib
from matplotlib.image import NonUniformImage
from mpl_toolkits.axes_grid1 import make_axes_locatable


# Local imports
import avaframe.in2Trans.shpConversion as shpConv
import avaframe.in2Trans.geoTrans as geoTrans
import avaframe.in3Utils.ascUtils as IOf
import avaframe.out3SimpPlot.outAIMEC as outAimec

# create local logger
log = logging.getLogger(__name__)

# -----------------------------------------------------------
# Aimec read inputs tools
# -----------------------------------------------------------
debugPlotFlag = False


def readAIMECinputs(avalancheDir, dirName='com1DFA'):
    """
    Reads the requiered files location for AIMEC postpocessing
    given an avalanche directory
    """
    cfgPath = {}
    pathPressure = os.path.join(avalancheDir, 'Work', 'ana3AIMEC', dirName, 'dfa_pressure')
    pathFlowHeight = os.path.join(avalancheDir, 'Work', 'ana3AIMEC', dirName, 'dfa_depth')
    pathMassBalance = os.path.join(avalancheDir, 'Work', 'ana3AIMEC', dirName, 'dfa_mass_balance')

    if not os.path.exists(pathMassBalance):
        os.makedirs(pathMassBalance)

    profileLayer = glob.glob(os.path.join(avalancheDir, 'Inputs', 'LINES', '*aimec*.shp'))
    cfgPath['profileLayer'] = ''.join(profileLayer)

    splitPointLayer = glob.glob(os.path.join(avalancheDir, 'Inputs', 'POINTS', '*.shp'))
    cfgPath['splitPointSource'] = ''.join(splitPointLayer)

    demSource = glob.glob(os.path.join(avalancheDir, 'Inputs', '*.asc'))
    try:
        assert len(demSource) == 1, 'There should be exactly one topography .asc file in ' + \
            avalancheDir + '/Inputs/'
    except AssertionError:
        raise
    cfgPath['demSource'] = ''.join(demSource)

    cfgPath['pressurefileList'] = getFileList(pathPressure)
    cfgPath['depthfileList'] = getFileList(pathFlowHeight)
    cfgPath['massfileList'] = getFileList(pathMassBalance)

    pathResult = os.path.join(avalancheDir, 'Outputs', 'AimecResults')
    cfgPath['pathResult'] = pathResult

    project_name = os.path.basename(avalancheDir)
    cfgPath['project_name'] = project_name
    path_name = os.path.basename(profileLayer[0])
    cfgPath['path_name'] = path_name
    cfgPath['dirName'] = 'com1DFA'

    return cfgPath


def getFileList(path2Folder):
    """ Get sorted list of all files in folder """
    fileList = [path2Folder +
                os.path.sep +
                str(name) for name in
                sorted(os.listdir(path2Folder)) if os.path.isfile(os.path.join(path2Folder, name))]
    return fileList

# -----------------------------------------------------------
# Aimec main
# -----------------------------------------------------------


def mainAIMEC(cfgPath, cfg):
    """
    Main logic for AIMEC postprocessing
    """

    # Extract input parameters
    cfgSetup = cfg['AIMECSETUP']
    cfgFlags = cfg['FLAGS']
    domainWidth = float(cfgSetup['domainWidth'])
    pressureLimit = float(cfgSetup['pressureLimit'])
    interpMethod = cfgSetup['interpMethod']

    log.info('Prepare data for post-ptocessing')
    # Make domain transformation
    log.info("Creating new deskewed raster and preparing new raster assignment function")
    raster_transfo = makeDomainTransfo(cfgPath, cfgSetup, cfgFlags)

    # transform pressure_data and depth_data in new raster
    newRasters = {}
    # assign pressure data
    log.info("Assigning pressure data to deskewed raster")
    newRasterPressure = assignData(cfgPath['pressurefileList'], raster_transfo,
                                   interpMethod)
    newRasters['newRasterPressure'] = newRasterPressure
    # assign depth data
    log.info("Assigning depth data to deskewed raster")
    newRasterDepth = assignData(cfgPath['depthfileList'], raster_transfo,
                                interpMethod)
    newRasters['newRasterDepth'] = newRasterDepth
    # assign dem data
    log.info("Assigning dem data to deskewed raster")
    newRasterDEM = assignData([cfgPath['demSource']], raster_transfo,
                              interpMethod)
    newRasters['newRasterDEM'] = newRasterDEM[0]

    # Analyze data
    log.info('Analyzing data')

    # analyze mass / entrainment
    log.info('Analyzing entrainment data')
    # determine growth index from entrainment data
    # [relMass, entMass, gr_index, gr_grad] = analyzeEntrainmentdata(cfgPath['massfileList'])
    gr_index = 0
    relMass = 0
    entMass = 0
    # analyze pressure_data and depth_data
    # determine runount, AMPP, AMD, FS,
    log.info('Analyzing data in path coordinate system')
    resAnalysis = analyzeData(raster_transfo, pressureLimit, newRasters, cfgPath, cfgFlags)

    # -----------------------------------------------------------
    # result visualisation + report
    # -----------------------------------------------------------
    log.info('Visualisation of results')
    outAimec.result_visu(cfgPath, raster_transfo, resAnalysis, pressureLimit)

    # -----------------------------------------------------------
    # write results to file
    # -----------------------------------------------------------
    log.info('Writing results to file')

    outAimec.result_write(cfgPath, cfgSetup, resAnalysis)

# -----------------------------------------------------------
# Aimec processing tools
# -----------------------------------------------------------


def makeDomainTransfo(cfgPath, cfgSetup, cfgFlags):
    """
    Make domain transformation :
    This function returns the information about this domain transformation
    Data given on a regular grid is projected on a nonuniform grid following
    a polyline

    input: cfgPath, cfgSetup, cfgFlags
    ouput: raster_transfo as a dictionary
            -(grid_x,grid_y) coordinates of the points of the new raster
            -(s,l) new coordinate System
            -(x,y) coordinates of the resampled polyline
            -rasterArea, real area of the cells of the new raster
            -indRunoutPoint start of the runout area

    """
    # Read input parameters
    rasterSource = cfgPath['pressurefileList'][0]
    demSource = cfgPath['demSource']
    ProfileLayer = cfgPath['profileLayer']
    outpath = cfgPath['pathResult']
    DefaultName = cfgPath['project_name']

    w = float(cfgSetup['domainWidth'])
    interpMethod = cfgSetup['interpMethod']

    log.info('Data-file %s analysed' % rasterSource)
    # read data
    # read raster data
    sourceData = IOf.readRaster(rasterSource)
    dem = IOf.readRaster(demSource)
    header = sourceData['header']
    xllcenter = header.xllcenter
    yllcenter = header.yllcenter
    cellsize = header.cellsize
    rasterdata = sourceData['rasterData']
    # read avaPath
    Avapath = shpConv.readLine(ProfileLayer, DefaultName, sourceData['header'])
    # read split point
    splitPoint = shpConv.readPoints(cfgPath['splitPointSource'], sourceData['header'])
    # add 'z' coordinate to the avaPath
    Avapath = geoTrans.projectOnRaster(dem, Avapath)
    # reverse avaPath if necessary
    _, Avapath = geoTrans.checkProfile(Avapath, projSplitPoint=None)

    log.info('Creating new raster along polyline: %s' % ProfileLayer)
    # Initialize transformation dictionary
    raster_transfo = {}

    # Get new Domain Boundaries DB
    # input: ava path
    # output: Left and right side points for the domain
    DB = geoTrans.path2domain(Avapath, w, header)

    # Make transformation matrix
    raster_transfo = makeTransfoMat(raster_transfo, DB, w, cellsize)

    # calculate the real area of the new cells as well as the s_coord
    raster_transfo = getSArea(raster_transfo)

    log.info('Size of rasterdata- old: %d x %d - new: %d x %d' % (
        np.size(rasterdata, 0), np.size(rasterdata, 1),
        np.size(raster_transfo['grid_x'], 0), np.size(raster_transfo['grid_x'], 1)))

    ##########################################################################
    # affect values
    raster_transfo['header'] = header
    # put back scale and origin
    raster_transfo['s'] = raster_transfo['s']*cellsize
    raster_transfo['l'] = raster_transfo['l']*cellsize
    raster_transfo['grid_x'] = raster_transfo['grid_x']*cellsize + header.xllcorner
    raster_transfo['grid_y'] = raster_transfo['grid_y']*cellsize + header.yllcorner
    raster_transfo['rasterArea'] = raster_transfo['rasterArea']*cellsize*cellsize
    # (x,y) coordinates of the resamples avapth (centerline where l = 0)
    n = np.shape(raster_transfo['l'])[0]
    indCenter = int(np.floor(n/2)+1)
    raster_transfo['x'] = raster_transfo['grid_x'][:, indCenter]
    raster_transfo['y'] = raster_transfo['grid_y'][:, indCenter]

    #################################################################
    # add 'z' coordinate to the centerline
    raster_transfo = geoTrans.projectOnRaster(dem, raster_transfo)
    # find projection of split point on the centerline centerline
    projPoint = geoTrans.findSplitPoint(raster_transfo, splitPoint)
    raster_transfo['indSplit'] = projPoint['indSplit']
    # prepare find start of runout area points
    runoutAngle = 20
    _, tmp, delta_ind = geoTrans.prepareFind10Point(runoutAngle, raster_transfo)
    # find the runout point: first point under runoutAngle
    indRunoutPoint = geoTrans.find10Point(tmp, delta_ind)
    raster_transfo['indRunoutPoint'] = indRunoutPoint

    aval_data = transform(rasterSource, raster_transfo, interpMethod)

    ###########################################################################
    # visualisation
    input_data = {}
    input_data['aval_data'] = aval_data
    input_data['sourceData'] = sourceData
    input_data['Avapath'] = Avapath
    input_data['DB'] = DB

    outAimec.visu_transfo(raster_transfo, input_data, cfgPath, cfgFlags)

    return raster_transfo


def split_section(DB, i):
    """
    Splits the ith segment of domain DB in the s direction
    (direction of the path)
    input: - DB domain Boundary dictionary
           - i number of the segment of DB to split
    ouput: - (x,y) coordinates of the ith left and right splited Boundaries
            (bxl, byl, bxr, byr)
            - m number of ellements on the new segments
    """
    # left edge
    xl0 = DB['DB_x_l'][i]
    xl1 = DB['DB_x_l'][i+1]
    yl0 = DB['DB_y_l'][i]
    yl1 = DB['DB_y_l'][i+1]
    dxl = xl1 - xl0
    dyl = yl1 - yl0
    Vl = np.array((dxl, dyl))
    zl = np.linalg.norm(Vl)

    # right edge
    xr0 = DB['DB_x_r'][i]
    xr1 = DB['DB_x_r'][i+1]
    yr0 = DB['DB_y_r'][i]
    yr1 = DB['DB_y_r'][i+1]
    dxr = xr1 - xr0
    dyr = yr1 - yr0
    Vr = np.array((dxr, dyr))
    zr = np.linalg.norm(Vr)

    # number of segments
    m = int(max(np.ceil(zl), np.ceil(zr))+1)
    # make left segment
    bxl = np.linspace(xl0, xl1, m)
    byl = np.linspace(yl0, yl1, m)
    # make right segment
    bxr = np.linspace(xr0, xr1, m)
    byr = np.linspace(yr0, yr1, m)

    return bxl, byl, bxr, byr, m


def makeTransfoMat(raster_transfo, DB, w, cellsize):
    """ Make transformation matrix.
        Takes a Domain Boundary and finds the (x,y) coordinates of the new
        raster point (the one following the path)
        input: - raster_transfo dictionary to fill in output
               - DB domain Boundary dictionary
               - w domain width
               - cellsize
        ouput: raster_transfo dictionary updated with the (grid_x,grid_y)
                coordinates of the new raster points
    """
    # number of points describing the avaPath
    n_pnt = np.shape(DB['DB_x_r'])[0]
    # Working with no dimentions (the cellsize scaling will be readded at the end)
    # l_coord is the distance from the polyline (cross section)
    # maximum step should be smaller then the cellsize
    n_total = np.ceil(w/cellsize)
    # take the next odd integer. This ensures that the l_coord = 0 exists
    n_total = int(n_total+1) if ((n_total % 2) == 0) else int(n_total)
    n_2tot = int(np.floor(n_total/2))
    l_coord = np.linspace(-n_2tot, n_2tot, n_total)  # this way, 0 is in l_coord

    # initialize new_rasters
    new_grid_raster_x = np.array([])  # x_coord of the points of the new raster
    new_grid_raster_y = np.array([])  # y_coord of the points of the new raster
    # loop on each section of the path
    for i in range(n_pnt-1):
        # split edges in segments
        bxl, byl, bxr, byr, m = split_section(DB, i)
        # bxl, byl, bxr, byr reprensent the s direction (olong path)
        # loop on segments of section
        for j in range(m-1):
            # this is the cross section segment (l direction)
            x = np.linspace(bxl[j], bxr[j], n_total)  # line coordinates x
            y = np.linspace(byl[j], byr[j], n_total)  # line coordinates y
            # save x and y coordinates of the new raster points
            if i == 0 and j == 0:
                new_grid_raster_x = x.reshape(1, n_total)
                new_grid_raster_y = y.reshape(1, n_total)
            else:
                new_grid_raster_x = np.append(new_grid_raster_x, x.reshape(1, n_total), axis=0)
                new_grid_raster_y = np.append(new_grid_raster_y, y.reshape(1, n_total), axis=0)

    # add last column
    x = np.linspace(bxl[m-1], bxr[m-1], n_total)  # line coordinates x
    y = np.linspace(byl[m-1], byr[m-1], n_total)  # line coordinates y
    new_grid_raster_x = np.append(new_grid_raster_x, x.reshape(1, n_total), axis=0)
    new_grid_raster_y = np.append(new_grid_raster_y, y.reshape(1, n_total), axis=0)

    raster_transfo['l'] = l_coord
    raster_transfo['grid_x'] = new_grid_raster_x
    raster_transfo['grid_y'] = new_grid_raster_y

    return raster_transfo


def getSArea(raster_transfo):
    """
    Find the s_coord corresponding to the transformation and the Area of
    the cells of the new raster
    input: - raster_transfo dictionary to fill in output
    ouput: raster_transfo dictionary updated with the s_coord
            coordinate and the area of the cells of the new raster
    """
    x_coord = raster_transfo['grid_x']
    y_coord = raster_transfo['grid_y']
    # add ghost lines and columns to the coord matrix
    # in order to perform dx and dy calculation
    n, m = np.shape(x_coord)
    x_coord = np.append(x_coord, x_coord[:, -2].reshape(n, 1), axis=1)
    y_coord = np.append(y_coord, y_coord[:, -2].reshape(n, 1), axis=1)
    n, m = np.shape(x_coord)
    x_coord = np.append(x_coord, x_coord[-2, :].reshape(1, m), axis=0)
    y_coord = np.append(y_coord, y_coord[-2, :].reshape(1, m), axis=0)
    n, m = np.shape(x_coord)
    # calculate dx and dy for each point in the l direction
    dxl = x_coord[0:n-1, 1:m]-x_coord[0:n-1, 0:m-1]
    dyl = y_coord[0:n-1, 1:m]-y_coord[0:n-1, 0:m-1]
    # calculate dx and dy for each point in the s direction
    dxs = x_coord[1:n, 0:m-1]-x_coord[0:n-1, 0:m-1]
    dys = y_coord[1:n, 0:m-1]-y_coord[0:n-1, 0:m-1]
    # deduce the distance in s direction
    Vs2 = (dxs*dxs + dys*dys)
    Vs = np.sqrt(Vs2)

    # calculate area of each cell
    new_area_raster = np.abs(dxl*dys - dxs*dyl)
    raster_transfo['rasterArea'] = new_area_raster

    if debugPlotFlag:
        fig, ax1 = plt.subplots()
        cmap = copy.copy(matplotlib.cm.jet)
        cmap.set_bad(color='white')
        im1 = plt.imshow(new_area_raster, cmap, origin='lower')
        divider = make_axes_locatable(ax1)
        cax = divider.append_axes("right", size="5%", pad=0.1)
        fig.colorbar(im1, cax=cax)
        plt.show()

    # get s_coord
    ds = Vs[:, int(np.floor(m/2))-1]
    s_coord = np.cumsum(ds)-ds[0]
    raster_transfo['s'] = s_coord

    return raster_transfo


def transform(fname, raster_transfo, interpMethod):
    """
    Affect value to the points of the new raster (after domain transormation)
    input:
            -fname = name of rasterfile to transform
            -raster_transfo = transformation info
            -interpolation method to chose between 'nearest' and 'bilinear'
    ouput:
            -new_data = z, pressure or depth... corresponding to fname on the new raster
    """
    name = os.path.basename(fname)
    data = IOf.readRaster(fname)

    # read tranformation info
    new_grid_raster_x = raster_transfo['grid_x']
    new_grid_raster_y = raster_transfo['grid_y']

    n, m = np.shape(new_grid_raster_x)
    xx = new_grid_raster_x
    yy = new_grid_raster_y
    Points = {}
    Points['x'] = xx.flatten()
    Points['y'] = yy.flatten()
    Points, i_ib, i_oob = geoTrans.projectOnRaster_Vect(data, Points, interp=interpMethod)
    new_data = Points['z'].reshape(n, m)
    log.info('Data-file: %s - %d raster values transferred - %d out of original raster bounds!' %
             (name, i_ib-i_oob, i_oob))

    return new_data


def assignData(fnames, raster_transfo, interpMethod):
    """
    Affect value to the points of the new raster (after domain transormation)
    input:
            -fnames = list of names of rasterfiles to transform
            -raster_transfo = transformation info
            -interpolation method to chose between 'nearest' and 'bilinear'
    ouput: aval_data = z, pressure or depth... corresponding to fnames on the new rasters
    """

    maxtopo = len(fnames)
    aval_data = np.array(([None] * maxtopo))

    log.info('Transfer data of %d file(s) from old to new raster' % maxtopo)
    for i in range(maxtopo):
        fname = fnames[i]
        aval_data[i] = transform(fname, raster_transfo, interpMethod)

    return aval_data


# -----------------------------------------------------------
# Aimec analysis tools
# -----------------------------------------------------------

def analyzeData(raster_transfo, p_lim, newRasters, cfgPath, cfgFlags):
    """
    Analyse pressure and depth deskewed data
    """

    resAnalysis = analyzePressureDepth(raster_transfo, p_lim, newRasters, cfgPath)

    resAnalysis = analyzeArea(raster_transfo, resAnalysis, p_lim, newRasters, cfgPath)

    outAimec.visu_runout(raster_transfo, resAnalysis, p_lim, newRasters, cfgPath, cfgFlags)

    return resAnalysis


def analyzePressureDepth(raster_transfo, p_lim, newRasters, cfgPath):
    """
    Analyse pressure and depth.
    Calculate runout, Max Peak Pressure, Average PP... same for depth
    Get mass and entrainement
    """
    # read inputs
    fname = cfgPath['pressurefileList']
    fname_mass = cfgPath['massfileList']
    outpath = cfgPath['pathResult']

    dataPressure = newRasters['newRasterPressure']
    dataDepth = newRasters['newRasterDepth']
    dataDEM = newRasters['newRasterDEM']
    s_coord = raster_transfo['s']
    l_coord = raster_transfo['l']
    rasterArea = raster_transfo['rasterArea']
    indRunoutPoint = raster_transfo['indRunoutPoint']
    sBeta = s_coord[indRunoutPoint]

    resAnalysis = {}

    # initialize Arrays
    n_topo = len(fname)
    runout = np.empty((n_topo))
    runout_mean = np.empty((n_topo))
    ampp = np.empty((n_topo))
    mmpp = np.empty((n_topo))
    amd = np.empty((n_topo))
    mmd = np.empty((n_topo))
    elevRel = np.empty((n_topo))
    deltaH = np.empty((n_topo))
    grIndex = np.empty((n_topo))
    grGrad = np.empty((n_topo))
    releaseMass = np.empty((n_topo))
    entrainedMass = np.empty((n_topo))

    n = np.shape(l_coord)[0]
    p_cross_all = np.zeros((n_topo, len(s_coord)))
    log.info('{: <15} {: <15} {: <15} {: <15}'.format(
        'Sim number ', 'rRunout ', 'rampp ', 'ramd ', 'FS'))
    # For each data set
    for i in range(n_topo):
        rasterdataPres = dataPressure[i]
        rasterdataDepth = dataDepth[i]

        # get mean max for each cross section for pressure
        # presCrossMean = np.nansum(rasterdataPres*rasterArea, axis=1)/np.nansum(rasterArea, axis=1)
        presCrossMean = np.nanmean(rasterdataPres, axis=1)
        presCrossMax = np.nanmax(rasterdataPres, 1)
        # also get the Area corresponding to those cells
        ind_presCrossMax = np.nanargmax(rasterdataPres, 1)
        ind_1 = np.arange(np.shape(rasterdataPres)[0])
        AreapresCrossMax = rasterArea[ind_1, ind_presCrossMax]
        # get mean max for each cross section for pressure
        # dCrossMean = np.nansum(rasterdataDepth*rasterArea, axis=1)/np.nansum(rasterArea, axis=1)
        dCrossMean = np.nanmean(rasterdataDepth, axis=1)
        dCrossMax = np.nanmax(rasterdataDepth, 1)
        # also get the Area corresponding to those cells
        ind_dCrossMax = np.nanargmax(rasterdataDepth, 1)
        ind_1 = np.arange(np.shape(rasterdataDepth)[0])
        AreadCrossMax = rasterArea[ind_1, ind_dCrossMax]

        p_cross_all[i] = presCrossMax
        #   Determine runout according to maximum and averaged values
        # search in max values
        lindex = np.nonzero(presCrossMax > p_lim)[0]
        if lindex.any():
            cupper = min(lindex)
            clower = max(lindex)
        else:
            log.error('No average pressure values > threshold found. threshold = %10.4f, too high?' % p_lim)
            cupper = 0
            clower = 0
        # search in mean values
        lindex = np.nonzero(presCrossMean > p_lim)[0]
        if lindex.any():
            cupper_m = min(lindex)
            clower_m = max(lindex)
        else:
            log.error('No average pressure values > threshold found. threshold = %10.4f, too high?' % p_lim)
            cupper_m = 0
            clower_m = 0
        # Mean max dpp of Cross-Section
        ampp[i] = np.nansum((presCrossMax*AreapresCrossMax)[cupper:clower+1]) / \
            np.nansum(AreapresCrossMax[cupper:clower+1])
        mmpp[i] = max(presCrossMax[cupper:clower+1])

        amd[i] = np.nansum((dCrossMax*AreadCrossMax)[cupper:clower+1]) / \
            np.nansum(AreadCrossMax[cupper:clower+1])
        mmd[i] = max(dCrossMax[cupper:clower+1])
    #    Runout
        runout[i] = s_coord[clower] - sBeta
        runout_mean[i] = s_coord[clower_m] - sBeta

        elevRel[i] = dataDEM[cupper, int(np.floor(n/2)+1)]
        deltaH[i] = dataDEM[cupper, int(np.floor(n/2)+1)] - dataDEM[clower, int(np.floor(n/2)+1)]

        # analyze mass
        releaseMass[i], entrainedMass[i], grIndex[i], grGrad[i] = read_write(fname_mass[i])
        if not (releaseMass[i] == releaseMass[0]):
            log.warning('Release masses differs between simulations!')

        # log.info('%s\t%10.4f\t%10.4f\t%10.4f' % (i+1, runout[i], ampp[i], amd[i]))
        log.info('{: <15} {:<15.4f} {:<15.4f} {:<15.4f}'.format(*[i+1, runout[i], ampp[i], amd[i]]))

    # affect values to output dictionary
    resAnalysis['runout'] = runout
    resAnalysis['runout_mean'] = runout_mean
    resAnalysis['AMPP'] = ampp
    resAnalysis['MMPP'] = mmpp
    resAnalysis['AMD'] = amd
    resAnalysis['MMD'] = mmd
    resAnalysis['elevRel'] = elevRel
    resAnalysis['deltaH'] = deltaH
    resAnalysis['relMass'] = releaseMass
    resAnalysis['entMass'] = entrainedMass
    resAnalysis['growthIndex'] = grIndex
    resAnalysis['growthGrad'] = grGrad
    resAnalysis['p_cross_all'] = p_cross_all

    return resAnalysis


def analyzeArea(raster_transfo, resAnalysis, p_lim, newRasters, cfgPath):
    """
    Compare results to reference.
    Compute True positive, False negative... areas.
    """
    fname = cfgPath['pressurefileList']

    dataPressure = newRasters['newRasterPressure']
    s_coord = raster_transfo['s']
    l_coord = raster_transfo['l']
    cellarea = raster_transfo['rasterArea']
    indRunoutPoint = raster_transfo['indRunoutPoint']

    # initialize Arrays
    n_topo = len(fname)
    TP = np.empty((n_topo))
    FN = np.empty((n_topo))
    FP = np.empty((n_topo))
    TN = np.empty((n_topo))

    # take first simulation as reference
    new_mask = copy.deepcopy(dataPressure[0])
    # prepare mask for area resAnalysis
    new_mask[0:indRunoutPoint] = 0
    new_mask[np.where(np.nan_to_num(new_mask) < p_lim)] = 0
    new_mask[np.where(np.nan_to_num(new_mask) >= p_lim)] = 1

    # comparison rasterdata with mask
    log.info('{: <15} {: <15} {: <15} {: <15} {: <15}'.format(
        'Sim number ', 'TP ', 'FN ', 'FP ', 'TN'))
    # rasterinfo
    n_start, m_start = np.nonzero(np.nan_to_num(new_mask))
    n_start = min(n_start)

    n_total = len(s_coord)
    m_total = len(l_coord)

    for i in range(n_topo):
        rasterdata = dataPressure[i]

        """
        area
        # true positive: reality(mask)=1, model(rasterdata)=1
        # false negative: reality(mask)=1, model(rasterdata)=0
        # false positive: reality(mask)=0, model(rasterdata)=1
        # true negative: reality(mask)=0, model(rasterdata)=0
        """
        # for each pressure-file p_lim is introduced (1/3/.. kPa), where the avalanche has stopped
        new_rasterdata = copy.deepcopy(rasterdata)
        new_rasterdata[0:indRunoutPoint] = 0
        new_rasterdata[np.where(np.nan_to_num(new_rasterdata) < p_lim)] = 0
        new_rasterdata[np.where(np.nan_to_num(new_rasterdata) >= p_lim)] = 1

        if debugPlotFlag and i > 0:
            figure_width = 2*10
            figure_height = 2*5
            lw = 1

            fig = plt.figure(figsize=(figure_width, figure_height), dpi=150)
            y_lim = s_coord[indRunoutPoint+20]+resAnalysis['runout'][0]
        #    for figure: referenz-simulation bei p_lim=1
            ax1 = plt.subplot(121)
            ax1.title.set_text('Reference Peak Presseure in the RunOut area')
            cmap = copy.copy(matplotlib.cm.jet)
            cmap.set_under(color='w')
            cmap.set_bad(color='k')
            im = NonUniformImage(ax1, extent=[l_coord.min(), l_coord.max(),
                                              s_coord.min(), s_coord.max()], cmap=cmap)
            im.set_clim(vmin=p_lim, vmax=np.max((dataPressure[0])[n_start:n_total+1]))
            im.set_data(l_coord, s_coord, dataPressure[0])
            ref0 = ax1.images.append(im)
            cbar = ax1.figure.colorbar(im, extend='both', ax=ax1, use_gridspec=True)
            cbar.ax.set_ylabel('peak pressure [kPa]')
            ax1.set_xlim([l_coord.min(), l_coord.max()])
            ax1.set_ylim([s_coord[indRunoutPoint-20], y_lim])
            ax1.set_xlabel('l [m]')
            ax1.set_ylabel('s [m]')

            ax2 = plt.subplot(122)
            ax2.title.set_text(
                'Difference between current and reference in the RunOut area\n  Blue = FN, Red = FP')
            colorsList = [[0, 0, 1], [1, 1, 1], [1, 0, 0]]
            cmap = matplotlib.colors.ListedColormap(colorsList)
            cmap.set_under(color='b')
            cmap.set_over(color='r')
            cmap.set_bad(color='k')
            im = NonUniformImage(ax2, extent=[l_coord.min(), l_coord.max(),
                                              s_coord.min(), s_coord.max()], cmap=cmap)
            im.set_clim(vmin=-0.000000001, vmax=0.000000001)
            im.set_data(l_coord, s_coord, new_rasterdata-new_mask)
            ref0 = ax2.images.append(im)
            # cbar = ax2.figure.colorbar(im, ax=ax2, extend='both', use_gridspec=True)
            # cbar.ax.set_ylabel('peak pressure [kPa]')
            ax2.set_xlim([l_coord.min(), l_coord.max()])
            ax2.set_ylim([s_coord[indRunoutPoint-20], y_lim])
            ax2.set_xlabel('l [m]')
            ax2.set_ylabel('s [m]')
            # fig.tight_layout()
            plt.show()

        tpInd = np.where((new_mask[n_start:n_total+1] == True) &
                         (new_rasterdata[n_start:n_total+1] == True))
        fpInd = np.where((new_mask[n_start:n_total+1] == False) &
                         (new_rasterdata[n_start:n_total+1] == True))
        fnInd = np.where((new_mask[n_start:n_total+1] == True) &
                         (new_rasterdata[n_start:n_total+1] == False))
        tnInd = np.where((new_mask[n_start:n_total+1] == False) &
                         (new_rasterdata[n_start:n_total+1] == False))

        # Teilrasterpunkte
        tpCount = len(tpInd[0])
        fpCount = len(fpInd[0])
        fnCount = len(fnInd[0])
        tnCount = len(tnInd[0])

        # subareas
        tp = sum(cellarea[tpInd[0] + n_start, tpInd[1]])
        fp = sum(cellarea[fpInd[0] + n_start, fpInd[1]])
        fn = sum(cellarea[fnInd[0] + n_start, fnInd[1]])
        tn = sum(cellarea[tnInd[0] + n_start, tnInd[1]])

        # take reference (first simulation) as normalizing area
        area_sum = tp + fn

        TP[i] = tp
        FN[i] = fn
        FP[i] = fp
        TN[i] = tn

        log.info('{: <15} {:<15.4f} {:<15.4f} {:<15.4f} {:<15.4f}'.format(
            *[i+1, tp/area_sum, fn/area_sum, fp/area_sum, tn/area_sum]))

    resAnalysis['TP'] = TP
    resAnalysis['FN'] = FN
    resAnalysis['FP'] = FP
    resAnalysis['TN'] = TN

    return resAnalysis


def read_write(fname_ent):
    """
    Read mass balance files to get mass properties of the simulation
    (total mass, entrained mass...)
    """
    #    load data
    #    time, total mass, entrained mass
    mass_time = np.loadtxt(fname_ent, delimiter=',', skiprows=1)
    maxind, maxval = max(enumerate(mass_time[:, 1]),
                         key=operator.itemgetter(1))
    timeResults = [mass_time[0, 0], mass_time[maxind, 0], mass_time[-1, 0]]
    totMassResults = [mass_time[0, 1], mass_time[maxind, 1], mass_time[-1, 1]]
    entMassResults = [mass_time[0, 2], mass_time[maxind, 2], mass_time[-1, 2]]
    relMass = totMassResults[0]
    entMass = entMassResults[2]
#   growth results
    growthIndex = totMassResults[2]/totMassResults[0]
    growthGrad = (totMassResults[2] - totMassResults[0]) / (timeResults[2] - timeResults[0])
    return relMass, entMass, growthIndex, growthGrad
