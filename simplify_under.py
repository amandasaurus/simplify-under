"""
Iteratibvely simplify a polygon datasource.

Library for iteratively simplifying a geometry datasource until it has no more
than a specified number of points in each polygon
"""
from __future__ import division

import argparse
import fiona
import shapely.geometry
import logging
import sys

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def num_points_in_polygon(geom):
    """Return number of points in a shapely geometry."""
    if geom.is_empty:
        return 0

    if geom.type == 'Polygon':
        return len(geom.exterior.coords) + sum(len(interior.coords) for interior in geom.interiors)
    elif geom.type == 'MultiPolygon':
        return sum(num_points_in_polygon(poly) for poly in geom.geoms)


def reduce_points(geom, num_points):
    """
    Iteratively reduce the point.

    :param shapely.geometry geom: The geometry to simplify
    :param int num_points: The maximum number of points that should be in output
    :returns: a new geometry
    """
    if geom is None:
        return geom

    # find a min & max
    min, max = 0.0001, 1000
    new_geom = None

    # ensure our max is big enough
    while True:
        max_geom = geom.simplify(max, preserve_topology=False)
        max_geom_points = num_points_in_polygon(max_geom)
        if max_geom_points > num_points:
            max = max * 10
        else:
            break

    for step in range(1000):
        middle_value = ((max - min) / 2) + min
        new_geom = geom.simplify(middle_value, preserve_topology=False)
        middle_value_points = num_points_in_polygon(new_geom)

        if middle_value_points == num_points:
            # shortcut, success, this is as good as we can get
            return new_geom
        elif middle_value_points > num_points:
            logger.debug("Step {}, min={}, max={}, middle_value={}, middle_value_points={} TOO LARGE".format(step, min, max, middle_value, middle_value_points))
            min = middle_value
        elif middle_value_points < num_points:
            logger.debug("Step {}, min={}, max={}, middle_value={}, middle_value_points={} TOO SMALL".format(step, min, max, middle_value, middle_value_points))
            max = middle_value

        if abs(max - min) < 0.00001:
            logger.debug("close enough")
            return new_geom


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--num-points', type=int, help="Maximum points per object", required=True)
    parser.add_argument('inputfilename', help="Filename of the original, input file.")
    parser.add_argument('outputfilename', help="Filename to write the new, simplified file to")

    parser.add_argument('-d', '--debug', action='store_true', help="Print debugging information")

    args = parser.parse_args()

    if args.debug:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s: %(message)s'))
        logger.addHandler(handler)
    else:
        logger.addHandler(logging.NullHandler())


    with fiona.open(args.inputfilename) as source:
        logger.debug("opened %s", args.inputfilename)
        logger.debug("Source meta: %s", source.meta)

        with fiona.open(args.outputfilename, 'w', **source.meta) as sink:
            for row in source:
                num_points = sum(len(x) for x in row['geometry']['coordinates'])
                if num_points > args.num_points and False:
                    logger.debug("Reducing %s", row['properties'])
                    geom = shapely.geometry.shape(row['geometry'])
                    new_geom = reduce_points(geom, args.num_points)
                    row['geometry'] = shapely.geometry.mapping(new_geom)

                sink.write(row)

if __name__ == '__main__':
    main()
