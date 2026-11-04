# Navigation Reference — Foundational Geometry and Astronomy

Tier 1 anchor source for the Navigation tab.

## Shape of the Earth

The Earth is very nearly a sphere with a mean radius of 6,371 km.
Circumference around the equator is about 40,075 km.

Latitude is the angle north or south of the equator, 0° to 90°.
Longitude is the angle east or west of the Greenwich meridian, 0° to 180°.
One degree of latitude ≈ 111 km everywhere.
One degree of longitude ≈ 111 km × cos(latitude) — it shrinks towards the poles.
One nautical mile = one minute of latitude = 1,852 metres.

## Earth's Rotation

The Earth turns 360° in about 24 hours, so 15° of longitude per hour,
or 1° every 4 minutes. The sun appears to move across the sky at the same rate.

## Latitude from Polaris

Polaris (the North Star) sits within about 0.7° of the north celestial pole.
The angle of Polaris above the horizon equals your latitude in the Northern Hemisphere.
This follows from spherical geometry: the celestial pole is directly above the
geographic pole, and its altitude rises one degree for every degree you travel north.

In the Southern Hemisphere there is no bright pole star. The south celestial pole
is found from the Southern Cross: extend the long axis of the cross about 4.5 times
its length.

## Latitude from the Noon Sun

At local noon the sun is at its highest point.

    Latitude = 90° − sun's noon altitude + sun's declination
    (Northern Hemisphere, sun to the south.)

The sun's declination varies through the year from +23.44° (June solstice) to
−23.44° (December solstice), and is 0° at the equinoxes.

## Longitude from Time

If you know the time at Greenwich (UTC) when the sun is highest at your location:

    Longitude = (12:00 − local noon in UTC hours) × 15°
    Positive result = east, negative = west.

The equation of time can shift true solar noon by up to about ±16 minutes during the year.

## Great-Circle Distance (Haversine)

The shortest path between two points on a sphere is along a great circle.

    a = sin²(Δφ/2) + cos φ1 · cos φ2 · sin²(Δλ/2)
    c = 2 · atan2(√a, √(1 − a))
    d = R · c
    φ is latitude, λ is longitude, in radians. R = 6,371 km.

## Dead Reckoning

From a known starting point, position is estimated from heading, speed and time.

    Distance = speed × time
    North-south change = distance × cos(heading)
    East-west change = distance × sin(heading)
    (heading measured clockwise from true north)

Errors grow with time. Correct with a fix whenever possible.

## Magnetic Declination

A compass points to magnetic north, not true north. The angle between them is the
magnetic declination, which varies by place and drifts slowly over years.

    True bearing = magnetic bearing + east declination (or − west declination)

## Horizon Distance

    Distance to horizon (km) ≈ 3.57 × √(height of eye in metres)
