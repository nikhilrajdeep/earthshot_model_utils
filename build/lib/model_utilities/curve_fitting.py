import pandas as pd
import numpy as np

import matplotlib.pyplot as plt
import seaborn as sns

from scipy.optimize import curve_fit

# constants
c_to_co2 = (44/12) #conversion factor c to co2 equivalent

# chapman richards curve fit
def chapman_richards_set_ymax(x, k, p):
    """
    basic math for chapman richards curve fit with specified ymax

    Parameters
    ----------
    x : n by 2 array of independent variables. First column is time in years, second column is
        constant value of ymax for the site for all years
    k : [float]
        k parameter
    p : [float]
        p parameter
    
    Returns
    -------
    vector of y values
    """
    y = x[:,1] * np.power( (1 - np.exp(-k * x[:,0])), p)
    return y


def logistic_set_ymax(x, x_0, k):
    """
    basic math for logistic curve fit, called by curve_fit_func
    y(t) = c / (1 + a*exp(-b*t)) where t is age and c is the maximum biomass (here replaced c in numerator with 1 
    since multiply by max biomass)
    nice visual of effect of changing parameters: https://datascience.oneoffcoder.com/s-curve.html
    
    Parameters
    ----------
    x : vector of data x values
    a : [float]
        a parameter
    b : [float]
        b parameter
    
    Returns
    -------
    vector of y values
    """
    y = x[:,1] / (1 + np.exp(-k * (x[:,0] - x_0)))
    return y


def clean_biomass_data(input_df, d_type, rs_break=125, rs_young=0.285, rs_old=0.285, biomass_to_c=0.47):
    """
    Function to take dataframe of agb and possibly bgb. Fills in missing bgb according to supplied parameters.
    Averages measurements of the same age (how does this affect results?). Convert units to tCO2e/ha, based
    on units of input data.

    Parameters
    ----------
    input_df : [pandas dataframe]
                pandas dataframe with columns 'agb_t_ha', 'bgb_t_ha', 'agb_bgb_t_ha' for the biomass data at location
    d_type : [string]
            'biomass' if input_df contains biomass in t/ha
            'carbon' if input_df contains carbon in t/ha

    rs_break : [float]
                aboveground biomass at which the root-to-shoot ratio switches from young value to old value from IPCC tier 1 tables
    rs_young : [float]
               root-to-shoot ratio for young forests (with lower biomass than rs_break)
               default = 0.285, value from IPCC Tier 1 table for moist tropical forest with biomass < 125
    rs_old : [float]
              root-to-shoot ratio for old forests (with hiher biomass than rs_break)
              default = 0.285, value from IPCC Tier 1 table for moist tropical forests
    biomass_to_c : [float]
                    fraction of biomass that is C, here default is 0.47 but user can change for biome or location specific

    Returns
    ---------
    input_df : the dataframe that was cleaned inplace
    """
    # fill in missing bgb, agb+bgb ------------
    for i in range(0, input_df.shape[0]):

        # if have agb but not bgb or agb+bgb ... use root-to-shoot to get bgb ... agb+bgb is sum of cols 2,3
        if pd.notna(input_df.at[i, 'agb_t_ha']) & pd.isna(input_df.at[i, 'bgb_t_ha']) & pd.isna(
                input_df.at[i, 'agb_bgb_t_ha']):
            # if agb > rs_break then use rs_old, else use rs_young
            if input_df.at[i, 'agb_t_ha'] > rs_break:
                input_df.at[i, 'bgb_t_ha'] = input_df.at[i, 'agb_t_ha'] * rs_old
            else:
                input_df.at[i, 'bgb_t_ha'] = input_df.at[i, 'agb_t_ha'] * rs_young
            input_df.at[i, 'agb_bgb_t_ha'] = input_df.at[i, 'agb_t_ha'] + input_df.at[i, 'bgb_t_ha']

        # if have agb and bgb but not agb+bgb ... sum cols 2,3
        elif pd.notna(input_df.at[i, 'agb_t_ha']) & (pd.notna(input_df.at[i, 'bgb_t_ha'])) & pd.isna(
                input_df.at[i, 'agb_bgb_t_ha']):
            input_df.at[i, 'agb_bgb_t_ha'] = input_df.at[i, 'agb_t_ha'] + input_df.at[i, 'bgb_t_ha']

    # average plots of same age
    input_df = input_df.groupby(['age']).agg({'agb_t_ha': 'mean',
                                              'bgb_t_ha': 'mean',
                                              'agb_bgb_t_ha': 'mean'})
    input_df.reset_index(drop=False, inplace=True)

    # convert biomass to CO2e -----------------
    if (d_type == 'biomass'):
        input_df['agb_tCO2e_ha'] = input_df['agb_t_ha'] * biomass_to_c * c_to_co2
        input_df['bgb_tCO2e_ha'] = input_df['bgb_t_ha'] * biomass_to_c * c_to_co2
        input_df['agb_bgb_tCO2e_ha'] = input_df['agb_bgb_t_ha'] * biomass_to_c * c_to_co2
    else:
        input_df['agb_tCO2e_ha'] = input_df['agb_t_ha'] * c_to_co2
        input_df['bgb_tCO2e_ha'] = input_df['bgb_t_ha'] * c_to_co2
        input_df['agb_bgb_tCO2e_ha'] = input_df['agb_bgb_t_ha'] * c_to_co2

    return input_df



def curve_fit_set_ymax(input_df, y_max_agb_bgb, years_pred=100, curve_fun=chapman_richards_set_ymax,
                       n_mc=1000):
    """
    function to take agb+bgb observations, fit a curve to them, and predict an interpolated/extrapolated
    time series. Assumes the ymax parameter will be specified (this could be made more general to handle
    the case where it's not).
    
    Parameters
    ----------
    input_df : [pandas dataframe]
                pandas dataframe with column 'agb_bgb_tCO2e_ha' for the biomass data at location
    y_max_agb_bgb : [float]
                    maximum biomass from mature forest in tCO2e/ha
    years_pred : [integer]
                 length of time series to predict (years)
    curve_fun : [function]
                the curve fit function to use
                chapman_richards_set_ymax
                logistic_set_ymax
    n_mc : [integer]
           number of monte carlo ensemble members

    To do: color plot by author column

    Returns
    -------
    output[0] : plot of chapman richards curve with data points displayed
    output[1] : table of projected C accumulation with columns age (1-100) and tCO2e/ha
    """

    # prepare data for curve fit -----------
    age = np.array(input_df['age']).reshape((input_df['age'].shape[0],1))
    agb_bgb_tco2_ha = input_df['agb_bgb_tCO2e_ha']

    y_max_array = np.ones_like(age) * y_max_agb_bgb
    x_data = np.concatenate((age, y_max_array), axis=1)

    # curve fit
    # find parameters k and p
    if curve_fun == logistic_set_ymax:
        L_estimate = agb_bgb_tco2_ha.max()
        x_0_estimate = np.median(age)
        k_estimate = 1.0
        #p_0 = [L_estimate, x_0_estimate, k_estimate]
        p_0 = [x_0_estimate, k_estimate]
        params, covar = curve_fit(logistic_set_ymax, 
                                  x_data, 
                                  agb_bgb_tco2_ha, 
                                  p_0, 
                                  method='dogbox',
                                  bounds=((-np.inf,0.1),(np.inf,5)))
    elif curve_fun == chapman_richards_set_ymax:
            params, covar = curve_fit(f=chapman_richards_set_ymax, 
                                      xdata=x_data, 
                                      ydata=agb_bgb_tco2_ha,
                                      bounds=((0,1),(np.inf,np.inf))) #k, p

    # Generate prediction ------------
    x_plot = np.arange(1,years_pred+1,1).reshape((years_pred,1))
    y_max_array_plot = np.ones_like(x_plot) * y_max_agb_bgb
    x_data_plot = np.concatenate((x_plot, y_max_array_plot), axis=1)

    if curve_fun == logistic_set_ymax:
        pred_agb_bgb = logistic_set_ymax(x_data_plot, x_0=params[0], k=params[1])
        #pred_agb_bgb = logistic_fun(x_data_plot, L=params[0], x_0=params[1], k=params[2])
    elif curve_fun == chapman_richards_set_ymax:
        pred_agb_bgb = chapman_richards_set_ymax(x=x_data_plot, k=params[0], p=params[1])

    # output predictions ---------------
    df_out = pd.DataFrame({'Age': x_plot.reshape(1, years_pred).tolist()[0],
                           'tCO2/ha': pred_agb_bgb.reshape(1, years_pred).tolist()[0]})

    if n_mc > 0:
        # Make Monte Carlo ensemble, get median and 95% CI bounds
        sample = np.random.default_rng().multivariate_normal(mean=params, cov=covar, size=n_mc).T
        series_list = []
        counter = 1
        if curve_fun == logistic_set_ymax:
            for x_0, k in zip(sample[0, :], sample[1, :]):
                pred = logistic_set_ymax(x=x_data_plot, x_0=x_0, k=k)
                series_list.append(pd.Series(data=pred, name=f'sim_{counter}'))
                counter += 1
        elif curve_fun == chapman_richards_set_ymax:
            for k, p in zip(sample[0, :], sample[1, :]):
                pred = chapman_richards_set_ymax(x=x_data_plot, k=k, p=p)
                series_list.append(pd.Series(data=pred, name=f'sim_{counter}'))
                counter += 1

        df_mc = pd.concat(series_list, axis=1)
        df_out[[0.025, 0.5, 0.975]] = df_mc.quantile(q=[0.025, 0.5, 0.975], axis=1).transpose()

    # Make plot ----------------
    c_fig, ax = plt.subplots(figsize=(15,5))

    ax.set_title('AGB+BGB estimates (tCO2e/ha) over the next 100 years', fontsize=15)
    ax.set_ylabel('AGB+BGB estimate (tCO2e/ha)', fontsize=15)
    ax.set_xlabel('Age', fontsize=15)
    ax.plot(x_plot, pred_agb_bgb)
    ax.scatter(age, agb_bgb_tco2_ha, color='orange')

    if n_mc > 0:
        df_out.plot(y=[0.025, 0.5, 0.975], x='Age', linestyle='--', ax=ax)

    return c_fig, df_out