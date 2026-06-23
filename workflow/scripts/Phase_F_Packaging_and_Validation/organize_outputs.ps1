param (
    [Parameter(Mandatory=$true)][string]$IncomingDataDir,
    [Parameter(Mandatory=$true)][string]$ModelsDir,
    [Parameter(Mandatory=$true)][string]$OutputDir
)

$baseDest = $OutputDir

# Clean start
if (Test-Path $baseDest) { Remove-Item -Path $baseDest -Recurse -Force }
New-Item -ItemType Directory -Path $baseDest | Out-Null

# Category 1: Spatial Algorithms
$c1_Rivers = "$baseDest\1_Geoprocessed_OSM_Matching\Rivers"
$c1_WTP = "$baseDest\1_Geoprocessed_OSM_Matching\Water_Treatment_Plants"
$c1_WWTP = "$baseDest\1_Geoprocessed_OSM_Matching\Wastewater_Treatment_Plants"
New-Item -ItemType Directory -Path $c1_Rivers, $c1_WTP, $c1_WWTP -Force | Out-Null

Copy-Item "$IncomingDataDir\Natural\Rivers\RiversStreams_named.*" $c1_Rivers
Copy-Item "$IncomingDataDir\Infrastructure\Water Treatment\WaterTreatment_named.*" $c1_WTP
Copy-Item "$IncomingDataDir\Infrastructure\Wastewater Treatment Plant\WWTreatmentP_named.*" $c1_WWTP

# Category 2: Python Deterministic Extraction
$c2_Stats = "$baseDest\2_Python_RuleBased_Extraction\Statistics_Mauritius"
$c2_Aqua = "$baseDest\2_Python_RuleBased_Extraction\Aquastat_FAO"
$c2_HydroCons = "$baseDest\2_Python_RuleBased_Extraction\Hydrology_Books_Consolidated_Tables"
$c2_HydroBasin = "$baseDest\2_Python_RuleBased_Extraction\Hydrology_Books_Per_Basin_Flows"
New-Item -ItemType Directory -Path $c2_Stats, $c2_Aqua, $c2_HydroCons, $c2_HydroBasin -Force | Out-Null

Copy-Item "$IncomingDataDir\Natural\Hydrology\Mautitius Stats\extracted\*.csv" $c2_Stats
Copy-Item "$IncomingDataDir\Natural\Hydrology\Aquastat\*.csv", "$IncomingDataDir\Natural\Hydrology\Aquastat\*.geojson" $c2_Aqua
Copy-Item "$IncomingDataDir\Natural\Hydrology\Mauritius Hydrology Book\named_exports\consolidated\*.csv" $c2_HydroCons
Copy-Item "$IncomingDataDir\Natural\Hydrology\Mauritius Hydrology Book\named_exports\separate\flows\*.csv" $c2_HydroBasin

# Category 3: AI & Visual Extraction
$c3_Fused = "$baseDest\3_Vision_AI_and_Visual_Parsing\Fused_Ensemble_Isohyetal_Maps"
$c3_Gemini = "$baseDest\3_Vision_AI_and_Visual_Parsing\Gemini_Topology_Schematics"
New-Item -ItemType Directory -Path $c3_Fused, $c3_Gemini -Force | Out-Null

Copy-Item "$ModelsDir\FUSED_ENSEMBLE_BEST\isohyetal_maps_fused.json" $c3_Fused
Copy-Item "$ModelsDir\gemini_3_1_pro_BEST\schematic_diagrams_*.json" $c3_Gemini

Write-Output "Tree structured successfully."
