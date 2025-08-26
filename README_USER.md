Technology which can be run with a single click, or which can be turned into a self-service tool:
- Simulate parcel-level development across a section of the city
- Generate buildings based on parcel and lot setbacks - can accept a user override of lot_id, height
- Apply textures/surfaces to those buildings - can accept a user override of 40ftx40ft facade images, optionally overriden by parcel
- Generate a timelapse video of buildings being developed over the study period
- Generate a KMZ for use in Google Earth
- Generate a USDZ for use in iOS ARKit

Workflows which I've defined that could allow users to self-service based on the above:
1. Generate "before" and "after" images for populating a website like emunsing.github.io  - [howto recording on Loom here](https://www.loom.com/share/70dcb85f9ac146a796eb1fdbf57f86e8?sid=260fba88-a545-4b85-b470-bbce8069fe8d)
2. Generate flythroughs in Google Earth and export to a video file - [howto recording on Loom here](https://www.loom.com/share/9bc5fc445e324ac285a53e570490f604?sid=5d2d8d36-7eb6-4b78-b5d7-30e8129ccc34) (examples: [Lombard St v1](https://drive.google.com/file/d/1ORxw_adA-5wLU1oTICcPHB30jEphvYuY/view?usp=drive_link) here, [Lombard St v2](https://drive.google.com/file/d/1VBQdDzL4E9UxiNS1UAmPqhTiXHbkq6bd/view?usp=drive_link) here, [Market St v1](https://drive.google.com/file/d/1ufZ-Xcv_oFkURGmWpnFHU5amWoXKmD39/view?usp=drive_link) here)
3. "drive" around in Google Earth to specific areas of interest (note: this should only be accessible to trained volunteers/staff)

This means that trained volunteers could provide the following for any community meetings:
- Images refuting the "Tofu" renderings from Neighborhoods United - Just need to find the corresponding viewpoint in Google Earth and use the workflow 1 above
- Renderings of multiple potential development scenarios for a neighborhood, varying in the specific parcels developed or in the surface/texture applied to each building - workflow 1 above
- Timelapse video of development
- "Before" and "after" images at key vistas, potentially with multiple versions showing different development scenarios or different building textures - workflow 1 above
- Fly-through video of key commercial corridors - workflow 2 above

To create good renderings where development appropriately targets soft sites, we need:
- Location of view of interest (e.g. "Castro street, looking east")
- CSV of parcel assessor block-lots expected to be developed (and expected height, if not the zoned height)
- CSV of parcel assessor block-lots which should be *excluded* from simulation (e.g. historical, rent-controlled, government buildings, etc)

We discussed the following but do not currently have a plan to complete the below technology:  This is not currently in my team's scope, and would need funding or a clear path-to-market.
- One-click workflow for generating buildings which comply with Objective Design Standards (currently implemented in Rhino with manual steps; could be replicated in Blender with ~2 engineer-days)
- Interactive, live interface for allowing citizens to change the style of the buildings
- Improving image quality by combining radiant field methods (e.g. Gaussian Splats) with 3d tiles and rendered buildings (probably would be 3-5 engineer-days; relatively low risk but uncertain quality)
- Improving image quality by combining on-site photos with rendered buildings, e.g. through an inferred depth map and mapping onto 3d tiles (probably would require 5-10 engineer-days; high quality but higher risk)

Different potential messaging/outreach strategies:
- Targeted imagery refuting NUSF tofu block vistas - use workflow 1 from above; @Kate Connally you should be able to self-service this with the linked KMZ files.
- Model 2-3 high-impact vistas very well
  - Likely requiring new technology development outlined above
  - Potentially including from different perspectives
- Model a large number of vistas with the existing pipeline, e.g. by working with local community orgs

Key stakeholders whose opinion will determine toolkit and strategy:
- Supervisor staff
- Community leaders of neighborhood orgs
- SF Planning Staff (I have reached out to Rachel Tanner, Lisa Chen, and Josh Switzky to ask for a list of high-priority vistas)