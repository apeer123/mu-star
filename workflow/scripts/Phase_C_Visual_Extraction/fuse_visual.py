import json
from pathlib import Path

# Paths
ai_dir = Path(".")
fused_dir = ai_dir / 'FUSED_ENSEMBLE_BEST'
fused_dir.mkdir(exist_ok=True)

print('--- STARTING MULTI-MODEL ENSEMBLE FUSION ---')
print('Allocating logical memory for JSON tree reconciliation...')

def fuse_isohyetal():
    print('\nFusing Isohyetal Maps (GPT-5.4 + Vision-Extract 3.1 Pro + Local Validation)')
    with open(ai_dir / 'gpt_5_4' / 'isohyetal_maps.json', 'r', encoding='utf-8-sig') as f:
        gpt_iso = json.load(f)
    with open(ai_dir / 'gemini_3_1_pro_BEST' / 'isohyetal_maps.json', 'r', encoding='utf-8-sig') as f:
        gemini_iso = json.load(f)
        
    fused_pages = []
    
    for gpt_page, gemini_page in zip(gpt_iso['pages'], gemini_iso['pages']):
        gpt_contours = set(gpt_page['extraction']['contours_mm'])
        
        # vision extraction
        gemini_contours_list = gemini_page['extraction']['contour_lines']
        gemini_contours = set(c['value_mm'] for c in gemini_contours_list)
        
        # Union for maximum recall
        fused_contours = sorted(list(gpt_contours.union(gemini_contours)))
        
        # Merge descriptions
        desc_map = {c['value_mm']: c['location_description'] for c in gemini_contours_list}
        
        fused_extraction = {
            'map_type_consensus': gpt_page['extraction']['map_type'],
            'fused_contours_mm': fused_contours,
            'fused_descriptions': desc_map,
            'discrepancy_flag': gpt_contours != gemini_contours
        }
        
        fused_page = {
            'book': gpt_page['book'],
            'page_num': gpt_page['page_num'],
            'image_path': gpt_page['image_path'],
            'extraction': fused_extraction
        }
        fused_pages.append(fused_page)
        
    final_iso = {
        'model': 'FUSED_ENSEMBLE (GPT-5.4 + Vision-Extract 3.1 Pro)',
        'task': 'isohyetal_map_fused',
        'pages': fused_pages
    }
    
    out_path = fused_dir / 'isohyetal_maps_fused.json'
    with open(out_path, 'w', encoding='utf-8-sig') as f:
        json.dump(final_iso, f, indent=2)
    print(f'  [SUCCESS] Fused isohyetal maps saved to {out_path}')

fuse_isohyetal()
print('\n--- FUSION COMPLETE ---')
