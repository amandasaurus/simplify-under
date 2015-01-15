"""
Iteratibvely simplify a polygon datasource.

Library for iteratively simplifying a geometry datasource until it has no more
than a specified number of points in each polygon
"""
from __future__ import division

import argparse
import fiona
import shapely.geometry, shapely.wkt, shapely.wkb
import logging
import sys
from collections import defaultdict

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)



def num_points_in_polygon(geom):
    """Return number of points in a shapely geometry."""
    if geom is None or geom.is_empty:
        return 0

    if geom.type == 'Polygon':
        return len(geom.exterior.coords) + sum(len(interior.coords) for interior in geom.interiors)
    elif geom.type == 'MultiPolygon':
        return sum(num_points_in_polygon(poly) for poly in geom.geoms)


def num_points_in_polygons(geoms):
    return sum(num_points_in_polygon(geom) for geom in geoms)


def reduce_points(geom, num_points):
    """
    Iteratively reduce the point.

    :param shapely.geometry geom: The geometry to simplify
    :param int num_points: The maximum number of points that should be in output
    :returns: a new geometry
    """
    if geom is None:
        logger.debug("Got None argument, returning")
        return geom

    # Is it already under?
    these_num_points = num_points_in_polygon(geom)
    if these_num_points <= num_points:
        logger.debug("Objects already has %d points which is <= %d points", these_num_points, num_points)
        return geom

    # find a min & max
    min, max = 0.0001, 1000
    new_geom = None

    # ensure our max is big enough
    while True:
        max_geom = simplify(geom, max)
        max_geom_points = num_points_in_polygon(max_geom)
        if max_geom_points > num_points:
            max = max * 10
        else:
            break

    for step in range(1000):
        middle_value = ((max - min) / 2) + min
        new_geom = simplify(geom, middle_value)
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
            logger.debug("close enough, difference of %s", abs(max - min))
            return new_geom

    return new_geom

def simplify(geom, value, buffer=None):
    if geom is None or geom.is_empty:
        return geom

    if buffer is not None:
        geom = geom.buffer(buffer*value)

    #new_geom = geom.simplify(value, preserve_topology=False)
    #new_geom = rdp_python(geom, value)
    new_geom = simplify_via_postgis(geom, value)

    if new_geom.is_empty:
        # We shouldn't get empty geoms, so do it again with preserve_topology=True
        logger.debug("Turned a non-empty geometry into empty for value=%s", value)

    return new_geom

def rdp_python(geom, value):
    """Use the pure python RDP simplification value"""
    import rdp

    if geom.type == 'MultiPolygon':
        return shapely.geometry.MultiPolygon([rdp_python(poly, value) for poly in geom.geoms])

    #import pdb ; pdb.set_trace()
    assert geom.type == 'Polygon'

    exterior = rdp.rdp(geom.exterior.coords, value)
    interiors = [rdp.rdp(interior.coords, value) for interior in geom.interiors]
    # if an interior has been reduced to 2 points, then it would be invalid to use it as a LinearRing. However if it's 2 points, we can remove it because we presume that it's being simplified away
    interiors = [i for i in interiors if len(i) > 2]
    if len(interiors) == 0:
        interiors = None
    print exterior
    print interiors
    return shapely.geometry.Polygon(exterior, interiors)


def simplify_via_postgis(geom, value):
    import psycopg2
    connection = psycopg2.connect(dbname='rory')
    cursor = connection.cursor()

    query = "select ST_AsText(ST_Simplify('{}'::geometry, {}));".format(geom.wkb.encode("hex"), value)
    cursor.execute(query)
    new_geom_wkt = str(cursor.fetchone()[0])
    if new_geom_wkt is None or new_geom_wkt == 'None':
        new_geom_wkt = 'POLYGON EMPTY'
    new_geom = shapely.wkt.loads(new_geom_wkt)

    return new_geom
                   



def reduce_points_combined(geoms, num_points, buffer=None):
    """
    Iteratively reduce the points in the list of polygons.

    :param list of shapely.geometry geom: The list of geometries to simplify
    :param int num_points: The maximum number of points that should be in all polygons
    :param float buffer: If not None, add a buffer of this fraction of the value around the geom before simplification
    :returns: a new list of new polygons
    """
    if geoms is None or len(geoms) == 0:
        logger.debug("Got None or empty list, returning that")
        return geom

    # Is it already under?
    these_num_points = num_points_in_polygons(geoms)
    if these_num_points <= num_points:
        logger.debug("Objects already has %d points which is <= %d points", these_num_points, num_points)
        return geoms

    # find a min & max
    min, max = 0.0001, 1000
    new_geom = None

    # ensure our max is big enough
    for step in range(1000):
        max_geoms = [simplify(geom, max) for geom in geoms]
        max_geoms_points = num_points_in_polygons(max_geoms)
        if max_geoms_points > num_points:
            max = max * 10
        else:
            break

    for step in range(1000):
        middle_value = ((max - min) / 2) + min
        new_geoms = [simplify(geom, middle_value, buffer) for geom in geoms]
        middle_value_points = num_points_in_polygons(new_geoms)

        if middle_value_points == num_points:
            # shortcut, success, this is as good as we can get
            logger.debug("Step {}, min={}, max={}, middle_value={}, middle_value_points={} EXACTLY RIGHT".format(step, min, max, middle_value, middle_value_points))
            return new_geoms
        elif middle_value_points > num_points:
            logger.debug("Step {}, min={}, max={}, middle_value={}, middle_value_points={} TOO LARGE".format(step, min, max, middle_value, middle_value_points))
            min = middle_value
        elif middle_value_points < num_points:
            logger.debug("Step {}, min={}, max={}, middle_value={}, middle_value_points={} TOO SMALL".format(step, min, max, middle_value, middle_value_points))
            max = middle_value

        if abs(max - min) < 0.00001:
            logger.debug("Close enough, difference of %s using middle_value %s with %s points", abs(max - min), middle_value, middle_value_points)
            return new_geoms

    return new_geoms


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--num-points', type=int, help="Maximum points per object", required=True)
    parser.add_argument('inputfilename', help="Filename of the original, input file.")
    parser.add_argument('outputfilename', help="Filename to write the new, simplified file to")

    parser.add_argument('-d', '--debug', action='store_true', help="Print debugging information")

    parser.add_argument('-g', '--group-by', metavar="PROPERTY", help="Group objects by this property, and use the combined point count of this group to see if we have too many points.", default=None, required=False)
    parser.add_argument('-N', '--drop-null', action="store_true", help="Drop geometries/rows that have been simplified to empty geometries. By default the rows with empty/null geometries will be kept.", required=False)
    parser.add_argument('-B', '--buffer', type=float, default=None, help="Before simplification, add a buffer around the geometry as this fraction of the simplification param. If ommitted, no buffer is added. Used to clean up geometries before. e.g. -B 0.001 adds a buffer of 0.1% of the current simplification", required=False)

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
            if args.group_by is None:
                # Simple point count per object
                for row in source:
                    num_points = sum(len(x) for x in row['geometry']['coordinates'])
                    if num_points > args.num_points and False:
                        logger.debug("Reducing %s", row['properties'])
                        geom = shapely.geometry.shape(row['geometry'])
                        new_geom = reduce_points(geom, args.num_points)

                        is_null = new_geom is None or new_geom.is_empty
                        if is_null:
                            new_num_empty_geoms += 1
                            logger.debug("Object with these properties has been reduced to an empty geometry: %r", row['properties'])
                            row['geometry'] = None
                        else:
                            row['geometry'] = shapely.geometry.mapping(new_geom)

                    # And save this object
                    if args.drop_null:
                        if not is_null:
                            sink.write(row)
                    else:
                        sink.write(row)

            else:
                logger.debug("Grouping object by the key: %s", args.group_by)
                # We are grouping
                groups = defaultdict(list)
                for row in source:
                    groups[row['properties'][args.group_by]].append(row)

                num_groups = len(groups)
                logger.debug("Objects grouped. There are %d unique keys", num_groups)

                # Now simplify each group
                for idx, group_key in enumerate(groups):
                    objs = groups[group_key]
                    logger.debug("Group %d of %d: Simplifying all %d object(s) with %s=%s", idx, num_groups, len(objs), args.group_by, group_key)
                    # Extract shapes
                    # If the geometry is "None", then make it empty
                    old_num_empty_geoms = sum(1 if obj['geometry'] is None else 0 for obj in objs)
                    geoms = [(shapely.geometry.shape(obj['geometry']) if obj['geometry'] else None) for obj in objs]
                    # Simplify
                    #if group_key == 51477:
                    #    import pdb ; pdb.set_trace()
                    new_geoms = reduce_points_combined(geoms, args.num_points, buffer=args.buffer)
                    new_num_empty_geoms = 0

                    # Match up properties again
                    for obj, new_geom in zip(objs, new_geoms):
                        is_null = new_geom is None or new_geom.is_empty
                        if is_null:
                            new_num_empty_geoms += 1
                            logger.debug("Object with these properties has been reduced to an empty geometry: %r", obj['properties'])
                            obj['geometry'] = None
                        else:
                            obj['geometry'] = shapely.geometry.mapping(new_geom)

                        # And save this object
                        if args.drop_null:
                            if not is_null:
                                sink.write(obj)
                        else:
                            sink.write(obj)

                    if old_num_empty_geoms != new_num_empty_geoms:
                        logger.debug("New empty geoms! While processing %s=%s, the number of empty geometries has changed from %d to %d change of %d", args.group_by, group_key, old_num_empty_geoms, new_num_empty_geoms, (new_num_empty_geoms - old_num_empty_geoms))

if __name__ == '__main__':
    main()
