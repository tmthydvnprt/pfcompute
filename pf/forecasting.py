"""
forecasting.py

Assumption and Data Driven based forecasting calculation.  Assumption based forecasting is useful for quickly playing with or
understanding a concept; it can be used to evaluate various strategies without historical or real data.  Data driven
forecasting is useful for forecasting an actual financial situation based on historical data, either personal or economic.
The Data driven approach generates statistical models from real data and forecasts with random samples from the models.

project    : pf
version    : 0.0.0
status     : development
modifydate :
createdate :
website    : https://github.com/tmthydvnprt/pf
author     : tmthydvnprt
email      : tim@tmthydvnprt.com
maintainer : tmthydvnprt
license    : MIT
copyright  : Copyright 2016, tmthydvnprt
credits    :

"""

import numpy as np
import pandas as pd
import scipy.stats as st
from statsmodels.tsa.arima_model import ARIMA

import pf.util
from pf.constants import ARIMA_ORDERS


################################################################################################################################
# Forecasting Helpers
################################################################################################################################
def increase_pay(
        paycheck,
        gross_increase,
        retire_contribution_percent,
        employer_match_percent,
        employer_retire_percent
    ):
    """
    Estimate pay increase affect of paycheck values.

    Paycheck is a DataFrame containing at least the following columns:
        gross
        net
        pretex retire
        pretax detuct
        posttax loan
        employer_match
        employer_retire
        other
        tax
        taxable gross
        taxable net

    """
    # Calculate last tax percent
    percent_tax = paycheck['tax'] / paycheck['taxable gross']
    # Increased pay and retirement
    paycheck['gross'] = (1.0 + gross_increase) * paycheck['gross']
    paycheck['pretax retire'] = -retire_contribution_percent * paycheck['gross']
    # Recalculate taxable gross and then tax
    paycheck['taxable gross'] = paycheck[['gross', 'pretax deduct', 'pretax retire']].sum(axis=1)
    paycheck['tax'] = percent_tax * paycheck['taxable gross']
    # Recalculate net
    paycheck['net'] = paycheck[['gross', 'pretax deduct', 'pretax retire', 'posttax loan', 'tax','other']].sum(axis=1)
    # Recalculate employer match
    paycheck['employer_match'] = employer_match_percent * paycheck['gross']
    paycheck['employer_retire'] = employer_retire_percent * paycheck['gross']

    return paycheck

################################################################################################################################
# Assumption Based Forecasting
################################################################################################################################

def assumption_fi_forecast(
        income=50000.00,
        initial_balance=0.0,
        income_increase=0.03,
        savings_rate=0.50,
        withdrawal_rate=0.04,
        return_rate=0.05,
        age=23,
        life_expectancy=90,
        min_spending=0,
        max_spending=9e999,
        start=None,
        expense_increase=True
    ):
    """
    Financial Independance (Investment withdrawal > Living expenses) forecasting based purely on assumptions not real data.
    """

    # Calculate years to simulate
    years = (life_expectancy - age) + 1

    # Empty DataFrame to store results
    columns = ['Age', 'Balance', 'Income', 'Savings', 'Expenses', 'Return on Investment', 'Safe Withdrawal', '% FI', 'FI']
    cashflow_table = pd.DataFrame(
        data=np.zeros((years, len(columns))),
        index=range(years),
        columns=columns
    )
    # cashflow_table['FI'] = False
    cashflow_table.index.name = 'year'

    # Store initial balance
    cashflow_table.iloc[0]['Balance'] = initial_balance

    # Generate Cashflow table
    fi = False
    for i in cashflow_table.index:

        # Calculate savings and expenses
        yearly_savings = savings_rate * income
        if i == 0 or expense_increase:
            yearly_expenses = (1 - savings_rate) * income if not fi else cashflow_table.loc[i-1]['Safe Withdrawal']
            yearly_expenses = max(yearly_expenses, min_spending)
            yearly_expenses = min(yearly_expenses, max_spending)

        # store data
        cashflow_table.loc[i, 'Age'] = age + i
        cashflow_table.loc[i, 'Income'] = income
        cashflow_table.loc[i, 'Savings'] = yearly_savings
        cashflow_table.loc[i, 'Expenses'] = yearly_expenses

        # If not the first year
        if i >= 1:
            # Determine Return
            cashflow_table.loc[i, 'Return on Investment'] = return_rate * cashflow_table.loc[i-1]['Balance']
            # Growth balance
            cashflow_table.loc[i, 'Balance'] = (1 + return_rate) * cashflow_table.loc[i-1]['Balance']
            # Calculate safe withdrawal
            cashflow_table.loc[i, 'Safe Withdrawal'] = withdrawal_rate * cashflow_table.loc[i-1]['Balance']
            cashflow_table.loc[i, '% FI'] = 100.0 * cashflow_table.loc[i, 'Safe Withdrawal'] / cashflow_table.loc[i, 'Expenses']

            # Once withdrawal is greater than expenses, retire
            if cashflow_table.loc[i, 'Safe Withdrawal'] >= cashflow_table.loc[i-1]['Expenses']:
                fi = True
                # Remove withdrawal from blance for expenses
                cashflow_table.loc[i, 'Balance'] -= cashflow_table.loc[i]['Safe Withdrawal']

        if fi:
            # stop income
            income = np.nan
        elif i > 0:
            # Add yearly savings
            cashflow_table.loc[i, 'Balance'] += yearly_savings

            # increase income a little for next year
            income = (1 + income_increase) * income

        # Store boolean
        cashflow_table.loc[i, 'FI'] = fi

    # Turn Index into date if data available
    if start:
        cashflow_table['Date'] = pd.date_range(start=start, periods=len(cashflow_table.index), freq='A')
        cashflow_table = cashflow_table.reset_index().set_index('Date')

    return cashflow_table

################################################################################################################################
# Modeled Forecasting
################################################################################################################################
def arima_model(accounts):
    """Fit ARIMA models for each account"""

    # Model each account
    account_models = {}
    for account_type, account in accounts:
        account_data = accounts[(account_type, account)]
        account_data.name = account

        # ARIMA model order is unknown, so find the highest order that can be fit
        order = 0
        modeled = False
        while not modeled and order < len(ARIMA_ORDERS):
            try:
                model = ARIMA(account_data, order=ARIMA_ORDERS[order])
                results = model.fit()
                modeled = True
                account_models[(account_type, account)] = results
            except  (ValueError, np.linalg.LinAlgError):
                order += 1

    return account_models

def arima_forecast(account_models, start, **kwds):
    """Forecast accounts with ARIMA method"""

    # Determine times
    forecast_start = start
    forecast_end = start + pd.DateOffset(**kwds)

    # Forecast each account
    accounts_forecast = pd.DataFrame(columns=account_models.keys())
    for account_type, account in accounts_forecast:

        accounts_forecast[(account_type, account)] = account_models[(account_type, account)].predict(
            start=str(forecast_start.date()),
            end=str(forecast_end.date()),
            typ='levels'
        )

    return accounts_forecast

def dist_fit_model(accounts):
    """Build models for each account based on log change"""

    # Model each account
    account_models = {}
    for account_type, account in accounts:

        # Compute monthly change, ignoring Infs and NaNs
        account_pct_change = np.log(accounts[(account_type, account)]) \
            .pct_change() \
            .replace([-1.0, -np.inf, np.inf], np.nan) \
            .dropna()
        # Generate model
        model, params = pf.util.best_fit_distribution(account_pct_change)
        account_models[(account_type, account)] = (model, params)

    return account_models

def monte_carlo_forecast(accounts, account_models, start, number_of_runs=1000, **kwds):
    """Forecast accounts with Monte Carlo method from fit distributions"""

    # Determine times
    forecast_start = start
    forecast_end = start + pd.DateOffset(**kwds)
    forecast_dates = pd.date_range(forecast_start, forecast_end, freq='MS')

    # Empty Panel to store Monte Carlo runs
    account_forecast_runs = pd.Panel(
        data=np.zeros((number_of_runs, len(forecast_dates), len(account_models.keys()))),
        items=range(number_of_runs),
        major_axis=forecast_dates,
        minor_axis=account_models.keys()
    )

    # Forecast each account
    accounts_forecast = pd.DataFrame(columns=account_models.keys())
    for account_type, account in accounts_forecast:

        # Get initial account value
        init_value = accounts[(account_type, account)].iloc[-1]
        if any(init_value == _ for _ in [np.inf, -np.inf, np.nan]):
            init_value = 1.0

        # Get model
        model_name, params = account_models[(account_type, account)]
        model = getattr(st, model_name)

        if model:
            arg = params[:-2]
            loc = params[-2]
            scale = params[-1]

            # Forecast into future with Monte Carlo
            for run in xrange(number_of_runs):
                # Generate random variables
                forecast_rvs = model.rvs(loc=loc, scale=scale, size=len(forecast_dates), *arg)
                # Create Series of percent changes from random variables
                forecast_pct_change = pd.Series(forecast_rvs, index=forecast_dates)
                # Clip unrealistic changes larger than +/-50% in once month
                forecast_pct_change = forecast_pct_change.clip(-0.5, 0.5)
                # Forecast account as monthly percent change from last known account value
                forecast_pct = np.exp(forecast_pct_change.copy())
                forecast_pct[0] = forecast_pct[0] * init_value
                forecast = forecast_pct.cumprod()
                # Add to run storage
                account_forecast_runs[run][(account_type, account)] = forecast

    return account_forecast_runs
