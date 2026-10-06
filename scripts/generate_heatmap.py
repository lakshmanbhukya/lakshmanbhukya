#!/usr/bin/env python3
"""
Zero-dependency scraper and SVG generator for lakshmanbhukya's GitHub contribution calendar.
Runs locally and automatically via GitHub Actions daily cron.
"""

import os
import re
import urllib.request
from datetime import datetime, timezone

USERNAME = "lakshmanbhukya"

def fetch_contributions_html(username=USERNAME):
    url = f"https://github.com/users/{username}/contributions"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")

def parse_contributions(html):
    day_regex = re.compile(
        r'<td[^>]*data-date="(?P<date>\d{4}-\d{2}-\d{2})"[^>]*id="(?P<id>[^"]+)"[^>]*data-level="(?P<level>\d+)"[^>]*>'
    )
    tooltip_regex = re.compile(
        r'<tool-tip[^>]*for="(?P<for_id>[^"]+)"[^>]*>(?P<text>[^<]+)</tool-tip>'
    )
    
    tooltips_map = {}
    for match in tooltip_regex.finditer(html):
        for_id = match.group("for_id")
        text = match.group("text").strip()
        count_match = re.search(r'(\d+)\s+contribution', text)
        if count_match:
            tooltips_map[for_id] = int(count_match.group(1))
        else:
            tooltips_map[for_id] = 0
            
    days = []
    for match in day_regex.finditer(html):
        d_date = match.group("date")
        d_id = match.group("id")
        d_level = int(match.group("level"))
        d_count = tooltips_map.get(d_id, 0 if d_level == 0 else max(1, d_level))
        
        days.append({
            "date": d_date,
            "level": d_level,
            "count": d_count
        })
        
    total_match = re.search(r'([0-9,]+)\s+contributions?\s+in\s+(?:the\s+last\s+year|\d{4})', html)
    if total_match:
        total_contributions = int(total_match.group(1).replace(",", ""))
    else:
        total_contributions = sum(d["count"] for d in days)
        
    return days, total_contributions

def compute_streaks(days):
    if not days:
        return 0, 0
        
    sorted_days = sorted(days, key=lambda x: x["date"])
    current_streak = 0
    longest_streak = 0
    temp_streak = 0
    
    for day in sorted_days:
        if day["count"] > 0:
            temp_streak += 1
            if temp_streak > longest_streak:
                longest_streak = temp_streak
        else:
            temp_streak = 0
            
    for day in reversed(sorted_days):
        if day["count"] > 0:
            current_streak += 1
        else:
            break
            
    return current_streak, longest_streak

def build_heatmap_svg(days, total_count, current_streak, longest_streak, output_path):
    svg_w = 860
    svg_h = 220
    
    colors = {
        0: "#161b22",
        1: "#0e4429",
        2: "#006d32",
        3: "#26a641",
        4: "#39d353"
    }
    
    sorted_days = sorted(days, key=lambda x: x["date"])
    weeks = []
    current_week = []
    
    for day in sorted_days:
        dt = datetime.strptime(day["date"], "%Y-%m-%d")
        row_idx = (dt.weekday() + 1) % 7  # Sunday = 0
        if row_idx == 0 and current_week:
            weeks.append(current_week)
            current_week = []
        current_week.append((row_idx, day, dt))
        
    if current_week:
        weeks.append(current_week)
        
    weeks = weeks[-53:]
    cell_size = 10
    cell_gap = 3.2
    grid_start_x = 56
    grid_start_y = 80
    
    # Month labels
    month_labels = []
    last_month = None
    for col_idx, week in enumerate(weeks):
        for row_idx, day, dt in week:
            if row_idx == 0:
                month_name = dt.strftime("%b")
                if month_name != last_month and col_idx < 50:
                    x_pos = grid_start_x + (col_idx * (cell_size + cell_gap))
                    month_labels.append(f'<text x="{x_pos}" y="{grid_start_y - 8}" class="cal-label">{month_name}</text>')
                    last_month = month_name
                break
                
    # Day labels
    day_labels = [(1, "Mon"), (3, "Wed"), (5, "Fri")]
    day_label_xml = []
    for r_idx, lbl in day_labels:
        y_pos = grid_start_y + (r_idx * (cell_size + cell_gap)) + 8.5
        day_label_xml.append(f'<text x="24" y="{y_pos}" class="cal-label">{lbl}</text>')

    # Cell Rectangles
    cell_elements = []
    for col_idx, week in enumerate(weeks):
        col_delay = round(col_idx * 0.015, 3)
        col_cells = [f'    <g class="week-col" style="animation-delay: {col_delay}s;">']
        for row_idx, day, _ in week:
            x_pos = round(grid_start_x + (col_idx * (cell_size + cell_gap)), 1)
            y_pos = round(grid_start_y + (row_idx * (cell_size + cell_gap)), 1)
            fill_color = colors.get(day["level"], colors[0])
            title_text = f'{day["count"]} contributions on {day["date"]}'
            col_cells.append(
                f'      <rect x="{x_pos}" y="{y_pos}" width="{cell_size}" height="{cell_size}" rx="2" fill="{fill_color}"><title>{title_text}</title></rect>'
            )
        col_cells.append('    </g>')
        cell_elements.append("\n".join(col_cells))

    # Legend
    legend_x = svg_w - 180
    legend_y = svg_h - 22
    legend_cells = []
    for lvl in range(5):
        lx = legend_x + 36 + (lvl * (cell_size + 3))
        legend_cells.append(f'<rect x="{lx}" y="{legend_y - 9}" width="{cell_size}" height="{cell_size}" rx="2" fill="{colors[lvl]}"/>')
        
    legend_xml = f'''
    <g class="cal-label">
      <text x="{legend_x}" y="{legend_y}">Less</text>
      {"".join(legend_cells)}
      <text x="{legend_x + 105}" y="{legend_y}">More</text>
    </g>
    '''

    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w} {svg_h}" width="{svg_w}" height="{svg_h}">
  <defs>
    <style>
      @keyframes colEntrance {{
        0% {{ opacity: 0; transform: translateY(4px); }}
        100% {{ opacity: 1; transform: translateY(0); }}
      }}
      .week-col {{
        animation: colEntrance 0.3s ease-out forwards;
      }}
      .header-bg {{ fill: #161b22; }}
      .title-text {{ font-family: 'SF Mono', 'JetBrains Mono', Consolas, monospace; font-size: 12px; fill: #8b949e; }}
      .stats-text {{ font-family: 'SF Mono', 'JetBrains Mono', Consolas, monospace; font-size: 11.5px; fill: #94a3b8; }}
      .stat-highlight {{ fill: #38bdf8; font-weight: 600; }}
      .cal-label {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 9.5px; fill: #6e7681; }}
    </style>
    <linearGradient id="heatGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f141c"/>
      <stop offset="100%" stop-color="#0a0d14"/>
    </linearGradient>
  </defs>

  <!-- Container Frame -->
  <rect x="1" y="1" width="{svg_w - 2}" height="{svg_h - 2}" rx="12" fill="url(#heatGrad)" stroke="#30363d" stroke-width="1.2"/>

  <!-- Title Bar -->
  <path d="M 1 13 A 12 12 0 0 1 13 1 L {svg_w - 13} 1 A 12 12 0 0 1 {svg_w - 1} 13 L {svg_w - 1} 36 L 1 36 Z" class="header-bg"/>
  <line x1="1" y1="36" x2="{svg_w - 1}" y2="36" stroke="#21262d" stroke-width="1"/>

  <!-- Window Controls -->
  <circle cx="20" cy="18" r="5.5" fill="#ff5f56"/>
  <circle cx="38" cy="18" r="5.5" fill="#ffbd2e"/>
  <circle cx="56" cy="18" r="5.5" fill="#27ca40"/>

  <!-- Window Title -->
  <text x="{svg_w // 2}" y="22" text-anchor="middle" class="title-text">lakshman@github ~ $ ./contributions.sh</text>

  <!-- Stats Line -->
  <g class="stats-text">
    <text x="24" y="55">
      Total: <tspan class="stat-highlight">{total_count:,}</tspan> contributions in the last year
      <tspan fill="#4b5563"> • </tspan>
      Current Streak: <tspan class="stat-highlight">{current_streak}</tspan> days
      <tspan fill="#4b5563"> • </tspan>
      Longest Streak: <tspan class="stat-highlight">{longest_streak}</tspan> days
    </text>
  </g>

  <!-- Month & Day Labels -->
  {"".join(month_labels)}
  {"".join(day_label_xml)}

  <!-- Grid Cells -->
{chr(10).join(cell_elements)}

  <!-- Legend -->
  {legend_xml}
</svg>
'''
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"Successfully updated Heatmap SVG: {output_path}")

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    svg_path = os.path.join(base_dir, "contrib-heatmap.svg")
    
    print(f"Fetching contribution data for {USERNAME}...")
    html = fetch_contributions_html(USERNAME)
    days, total_count = parse_contributions(html)
    current_streak, longest_streak = compute_streaks(days)
    build_heatmap_svg(days, total_count, current_streak, longest_streak, svg_path)

if __name__ == "__main__":
    main()
