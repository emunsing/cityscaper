from shapely import plotting as shap_plot   
from cityscaper.autolot.utils import get_nearest_parcels
from cityscaper.autolot.parcel_analysis import get_sides_df
import matplotlib.pyplot as plt


def plot_edges(parcel_ser, blockid, ax=None, street_buffer=None, use_shortest_line=False, show_envelope=False, street_edges=None):
    target_parcel = parcel_ser.loc[blockid]
    nearest_parcels = get_nearest_parcels(parcel_ser, blockid, 25)
    if ax is None:
        fig, ax = plt.subplots(figsize=(16, 16))
    for block_id, parcel in nearest_parcels.items():
        shap_plot.plot_polygon(parcel, ax=ax, color='lightgray', alpha=0.7)

    if street_buffer is not None:
        sb0 = nearest_parcels.union_all().buffer(50).intersection(street_buffer)
        shap_plot.plot_polygon(sb0, ax=ax, color='lightblue', alpha=0.35)


    par = get_sides_df(parcel_ser, blockid, street_buffer=street_buffer, use_shortest_line=use_shortest_line, street_edges=street_edges)

    adj_color_mapper = {"parcel":"green", "front":"red", "other":"purple"}
    shap_plot.plot_points(par.front_midpoint, ax=ax, color='blue', alpha=0.7, marker='*', markersize=10)
    shap_plot.plot_points(par.rear_point, ax=ax, color='red', alpha=0.7, marker='8', markersize=10)

    if show_envelope:
        shap_plot.plot_polygon(par.target_parcel_envelope, ax=ax, color='lightgreen', alpha=0.2)

    shap_plot.plot_polygon(par.foot_print_double_buff, ax=ax, color='lightblue', alpha=0.5,
    )

    if par.rear_point is not None:
        shap_plot.plot_line(par.envelope_rear_setback, ax=ax, color='black', alpha=0.7, linewidth=1, add_points=False)

    for line, details in par.prop_rec.iterrows():
        shap_plot.plot_line(line, ax=ax, color=adj_color_mapper[details["adj"]], alpha=0.7, linewidth=4, add_points=False)

    if ax is not None:
        ax.set_title(blockid)
    return par.prop_rec