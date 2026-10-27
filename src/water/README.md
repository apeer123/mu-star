This readme explains how we are going to use this pywr solution:
The inputs to be made by the user is found in data folder.

They are namely:
1. catchment_data_monthly_m3.csv
2. costs.csv
3. basin_parameters.csv

For catchment_data_monthly_m3.csv , doing data entry , where fields such as 
date	YYYY-MM-01	Monthly timestamp across 46 years (552 monthly steps) where same has been populated with dummy data ,
catchment	Text (A to Z)	Catchment identifier (25 national basins, excluding O),
inflow Supply: Total natural runoff / river inflow volume entering the basin ,
demand_municipal	Demand (Priority 1): Domestic potable drinking water needed by residents ,
demand_industrial	Demand (Priority 2): Water needed by businesses, factories, and commercial units ,
demand_irrigation	Demand (Priority 3): Agricultural water needed for irrigation (sugarcane, crops).

Then we have cost csv which is about The policy and priority ranking managing water allocation.


Lastly, there is basin_parameters.csv, where for this one :

basin	Catchment is from (A through Z, omitting O) it	identifies the catchment.
reservoir_capacity_m3	is the Maximum dam storage capacity.	If NO reservoir exists: Enter 0.0. The catchment operates as a natural run-of-river basin.
dead_storage_m3	which is the	Minimum unusable water level at dam bottom.	If NO reservoir exists: Enter 0.0.
hydropower_max_m3	is about	Maximum turbine hydraulic throughput.	If NO hydropower plant exists: Enter 0.0. No power generation flow is recorded.
mrf_target_m3	is the	Minimum Residual Flow target volume.	If NO MRF target is required: Enter 0.0.
initial_storage_m3 is the Starting water volume at month 1.	If NO reservoir exists: Enter 0.0.



To execute the simulation, python model.py should be executed and output will be generated in its folder. Additionally, the json file would also be updated accordingly.
