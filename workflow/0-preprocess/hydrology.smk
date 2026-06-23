"""
Process hydrology data sources into tabular extracted data.
"""

rule extract_catchment_flows:
    """
    Extract annual discharge tables from the Mauritius Hydrology Data Book catchment PDFs.
    """
    input:
        pdfs = "{data}/incoming/hydrology/mauritius_hydrology_book/pdfs"
    output:
        extracted = directory("{data}/processed/hydrology/catchment_flows")
    shell:
        """
        python workflow/scripts/extract_catchment_flows.py \
            --indir "{input.pdfs}" \
            --outdir "{output.extracted}"
        """

rule extract_grse_flow_tables:
    """
    Extracts monthly flow tables from Hydrology Data Book Chapter 3 PDFs for all
    GRSE E-series stations.
    """
    input:
        images_dir = "{data}/incoming/hydrology/mauritius_hydrology_book/images",
        pdf_dir = "{data}/incoming/hydrology/mauritius_hydrology_book/pdfs"
    output:
        extracted = directory("{data}/processed/hydrology/grse_flow_tables")
    shell:
        """
        python workflow/scripts/extract_grse_flow_tables.py \
            --images-dir "{input.images_dir}" \
            --pdf-dir "{input.pdf_dir}" \
            --output-dir "{output.extracted}"
        """

rule extract_aquastat_dams:
    """
    Extract MUS-dams_eng.xlsx provided by Silvia Colombo / MSTAR project.
    """
    input:
        xlsx = "{data}/incoming/hydrology/aquastat/MUS-dams_eng.xlsx"
    output:
        extracted = directory("{data}/processed/hydrology/aquastat_dams")
    shell:
        """
        python workflow/scripts/extract_aquastat_dams.py \
            --xlsx "{input.xlsx}" \
            --out-dir "{output.extracted}"
        """

rule extract_mauritius_water_stats:
    """
    Extract water production and sales statistics from Mauritius Statistics.
    """
    input:
        stats_dir = "{data}/incoming/hydrology/mauritius_statistics"
    output:
        extracted = directory("{data}/processed/hydrology/mauritius_statistics_extracted")
    shell:
        """
        python workflow/scripts/extract_mauritius_water_stats.py \
            --stats-dir "{input.stats_dir}" \
            --out-dir "{output.extracted}"
        """

rule geocode_plants:
    """
    Reverse-geocodes WTP and WWTP coordinates via Nominatim OSM API.
    """
    input:
        coords_dir = "{data}/incoming/infrastructure/water_treatment"
    output:
        geocoded = directory("{data}/processed/infrastructure/geocoded_plants")
    shell:
        """
        python workflow/scripts/geocode_plants.py \
            --input_dir "{input.coords_dir}" \
            --output_dir "{output.geocoded}"
        """
