##################################
in2Trans: Module Project Utilities
##################################



geoTrans
===================
The ``geoTrans.py`` module gathers useful functions to operate transformations on raster, lines, points...

Functions
------------------------

**Projection on Raster:**

``Points = projectOnRaster(dem, Points)`` takes a "dem" dictionary and "Points" dictionary
(wich can be a single point or a line...) in input and returns the "Points" dictionary with
an extra "z" argument representing the "z" coordinate of the (x,y) point on the dem.


``Points = projectOnRasterVect(dem, Points, interp = 'bilinear')`` Does the same as the previous
function but also operates on 2D arrays. All the calculation are vectorized to avoid loops.
Two interpolation methods are available, 'nearest' or 'bilinear'


**Prepare Line:**

``AvaProfile, projSplitPoint = prepareLine(dem, AvaPath, distance=10, Point=None)`` takes a "dem" dictionary,
a "AvaPath" dictionary (x, y coordinates), a re-sampling distance and a "Point" dictionary in input and returns
the "AvaProfile" dictionary corresponding to the "AvaPath" dictionary. That is to say the "line" dictionary re-sampled
according to distance with the corresponding "z" argument representing the "z" coordinate of the re-sampled (x,y)
point on the dem and the curvilinear coordinate "s" along the line (the first point of the line has a s=0).
It also returns the projection of the Point on the AvaProfile if this one was supplied in input.

**Project on Profile:**

``projSplitPoint = findSplitPoint(AvaProfile, splitPoint)`` takes a "AvaProfile" dictionary
and a "splitPoint" dictionary in input and returns the "projSplitPoint" dictionary which is the projection of
"splitPoint" on the "AvaProfile".


**Check Profile:**

``projSplitPoint, AvaProfile = checkProfile(AvaProfile, projSplitPoint=None)`` takes a "AvaProfile" dictionary
and a "projSplitPoint" dictionary in input and check if the Profile goes from top to bottom,
reverts it if necessary and returns the correct "projSplitPoint" and "AvaProfile" dictionaries.

**Prepare inputs for find angle in profile:**

``angle, tmp, deltaInd =prepareAngleProfile(beta, AvaProfile)`` takes a angle value in degres and
an Avalanche profile in input, computes the angle of the profile and returns this ``angle``, the list
of indexes ``tmp`` where the angle is under the input angle value and ``deltaInd`` the number of consecutive
indexes required.

**Find angle in profile:**

``idsAnglePoint =findAngleProfile(tmp, deltaInd)`` takes the outputs of ``prepareAngleProfile`` as inputs
and returns the index of the desired angle as output.

**Bresenham Algorithm:**

``z = bresenfindCellsCrossedByLineBresenhamham(x0, y0, x1, y1, cs)`` takes a two (x,y) points and a cell size in input and returns
the z = (x,y) list of the cells hit by the line between the two input points.


**Path to domain:**

``rasterTransfo = path2domain(xyPath, rasterTransfo)`` takes the (x,y) coordinates of a polyline,
a domain width and a cell size (in rasterTransfo) in input and returns the domain of width w along the polyline.

**Polygon to mask:**

``mask = poly2mask_simple(ydep, xdep, ncols, nrows)`` takes the (x,y) coordinates
of a polygon and a rater size in input and returns the raster mask corresponding to the polygon.

**In polygon:**

``IN = inpolygon(X, Y, xv, yv)`` takes the (X, Y) coordinates of points and xv, yv foot print of a
polygon on a raster in input and returns the raster mask corresponding to the polygon.


Reading shape files
=============================

``shpConversion.py`` is a module created to handle shape files. It contains different functions
to read shape files to numpy arrays, either lines or points

Functions
------------------------

**Read shape file:**

``SHPdata = SHP2Array(fname, defname=None)`` takes a .shp file name as input (and eventualy a default name for the layer)
and returns a SHPdata dictionnary containing the layer information (can be multiple points or lines):
::

		SHPdata['Name'] = 'list of paths names'
		SHPdata['x'] = 'np array of the x coords of points in paths'
		SHPdata['y'] = 'np array of the y coords of points in paths'
		SHPdata['z'] = 'np array of the z coords of points in paths'
		SHPdata['Start'] = 'list of starting index of each Line in 'x''
		SHPdata['Length'] = 'list of length of each Line in 'x''

**Read shape file as Lines:**

``Line = readLine(fname, defname, header)`` takes a .shp file name as input,  a default name for the layer and a DEM header
reads the shape file, checks that the Lines lay on the DEM and returns the SHPdata dictionnary containing the Lines information.


**Read shape file as Points:**

``Points = readPoints(fname, header)`` takes a .shp file name as input,  a default name for the layer and a DEM header
reads the shape file, checks that the Lines lay on the DEM and returns the SHPdata dictionnary containing the Points information.
