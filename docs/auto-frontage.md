# AutoFrontage

How do we decide which side is the front?

## Simple lots

Defined by a lot bounded on 3 sides by other lots: look for the side not abutted directly with another parcel

## Corner lots

* Possible Approaches
    * Break down by size of lot
        * Small lots face smaller street, when there is a difference
        * big lots face larger street, when there is a difference
    * Could also use sidewalk width
        * [Dataset](https://data.sfgov.org/Transportation/Map-of-Sidewalk-Widths/ygcm-bt3x)

## Weird lots

Types:

* strange shapes
* alley ways
* abutting parks
    * are parks parcels?

How might we design? 

* existing footprint on abutting lots?
* physics based (one side is of min width, inflate the other and move around?)

# Set backs

* need strategy here
* definitely clip narrow peninsulas. 
    * what's a good rule for that?
* for non building space, default to grass
    * rules for adding trees or benches?
    * Cafe tables?