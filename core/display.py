import os
import sys
import time
import asyncio
import re
import logging

logger = logging.getLogger(__name__)

async def update_epaper_screen(db, total, captured, shared_state, picdir):
    """Initializes, draws the list of 6 strongest active networks, updates the display and sleeps."""
    try:
        from waveshare_epd import epd2in15g
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as e:
        logger.error(f"E-Paper library import failed inside task: {e}")
        return

    try:
        epd = epd2in15g.EPD()
        epd.init()
        
        font_path = os.path.join(picdir, 'Font.ttc')
        font_title = ImageFont.truetype(font_path, 18)
        font_text = ImageFont.truetype(font_path, 22)
        font_clients = ImageFont.truetype(font_path, 18)
        
        # E-Paper resolution is 296 (height) x 160 (width)
        Himage = Image.new('RGB', (epd.height, epd.width), epd.WHITE)
        draw = ImageDraw.Draw(Himage)
        
        # Fetch strongest active networks (excluding captured & banned ones)
        try:
            active_aps = await db.get_active_aps_with_status()
            # Filter out captured and banned networks
            active_aps_filtered = [
                ap for ap in active_aps 
                if 'przechwycono' not in ap.get('status', '').lower() 
                and ap.get('status', '').lower() not in ('zbanowany', 'banned', 'time_banned')
            ]
            # Sort first by client count (descending), then by RSSI (descending)
            active_aps_filtered.sort(key=lambda x: (x.get('client_count', 0), x.get('rssi', -120)), reverse=True)
            active_count = len(active_aps)
        except Exception as db_err:
            logger.error(f"Failed to fetch active APs: {db_err}")
            active_aps_filtered = []
            active_count = 0
            
        top_6 = active_aps_filtered[:6]

        # Top Status: Tempo & Captured counts
        try:
            rate, trend, since_last = db.get_discovery_rate()
            if since_last is None:
                sub_str = "brak"
            elif since_last == float('inf') or since_last == 99999:
                sub_str = "same znane"
            else:
                sub_str = f"nowe: {int(since_last)}s"
        except Exception:
            rate, trend, sub_str = 0.0, "—", "brak"

        # Draw Stats
        deauth_count = shared_state.get('global_deauth_count', 0)
        pmkid_count = shared_state.get('global_pmkid_count', 0)
        # Draw yellow bar background for TEMPO (widened by 2px: height becomes 22 -> y from 0 to 22)
        draw.rectangle([(0, 0), (epd.height, 22)], fill=epd.YELLOW)
        tempo_text = f"TEMPO: {rate}/min {trend} ({sub_str})"
        draw.text((10, 2), tempo_text, font=font_title, fill=epd.BLACK)
        draw.text((11, 2), tempo_text, font=font_title, fill=epd.BLACK)
        # Draw red bar background (shifted down to start at 23, ending at 45)
        draw.rectangle([(0, 23), (epd.height, 45)], fill=epd.RED)
        # Draw white text over the red bar (bold effect via 1px offset, centered at 25)
        char_241 = bytes([241]).decode('cp437')
        char_197 = bytes([197]).decode('cp437')
        status_text = f"{char_241}:{total} | up:{active_count} | ok:{captured} | {char_197}:{deauth_count} | p:{pmkid_count}"
        draw.text((10, 25), status_text, font=font_title, fill=epd.WHITE)
        draw.text((11, 25), status_text, font=font_title, fill=epd.WHITE)
        
        # Separator line (shifted to 46)
        draw.line([(0, 46), (epd.height, 46)], fill=epd.YELLOW, width=2)
        
        if not top_6:
            draw.text((20, 80), "Skanowanie w toku / brak sieci...", font=font_text, fill=epd.BLACK)
        else:
            y_pos = 48
            for ap in top_6:
                rssi = ap.get('rssi', 0)
                essid = ap.get('essid') or '<ukryta>'
                deauth = ap.get('liczba_atakow_deauth', 0)
                pmkid = ap.get('liczba_atakow_pmkid', 0)
                clients = ap.get('client_count', 0)
                score = ap.get('score', 0.0)
                
                # RSSI (negative sign removed)
                rssi_str = f"{abs(rssi)}"
                
                # Truncate ESSID to fit nicely
                essid_disp = essid[:9]
                
                # Attack status format
                atk_str = f"{deauth}/{pmkid}"
                
                # Format BRAIN score as integer value or default string
                try:
                    score_val = float(score)
                    score_disp = str(int(score_val))
                except (ValueError, TypeError):
                    score_disp = str(score)
                
                # Draw RSSI, ESSID, and attack counts (22 px)
                draw.text((8, y_pos), rssi_str, font=font_text, fill=epd.BLACK)
                draw.text((45, y_pos), essid_disp, font=font_text, fill=epd.BLACK)
                draw.text((170, y_pos), atk_str, font=font_text, fill=epd.BLACK)
                
                # Draw client count as a red digit (22 px)
                draw.text((220, y_pos), str(clients), font=font_text, fill=epd.RED)
                
                # Draw BRAIN score as a black digit/value (22 px) at the end
                draw.text((245, y_pos), score_disp, font=font_text, fill=epd.BLACK)
                
                y_pos += 18
            
        # Outer border removed (to gain pixels and stretch display area)
        
        epd.display(epd.getbuffer(Himage))
        epd.sleep()
        
    except Exception as e:
        logger.error(f"Error drawing E-Paper screen: {e}")

async def epaper_display_updater(db, shared_state):
    """Background task running alongside other main tasks to update E-Paper every 1 minute."""
    libdir = '/home/kali/e-Paper/RaspberryPi_JetsonNano/python/lib'
    picdir = '/home/kali/e-Paper/RaspberryPi_JetsonNano/python/pic'
    
    if os.path.exists(libdir):
        sys.path.append(libdir)
        
    # Check if Waveshare drivers are importable
    try:
        from waveshare_epd import epd2in15g
    except ImportError:
        logger.warning("Waveshare E-Paper library not found. Skipping E-Paper background task.")
        return

    # Seed initial values
    last_total_count = 0
    last_captured_count = 0
    try:
        last_total_count, last_captured_count = await db.get_stats()
    except Exception:
        pass
        
    # Initial startup draw
    try:
        if not shared_state.get('pause_eink', False):
            await update_epaper_screen(db, last_total_count, last_captured_count, shared_state, picdir)
    except Exception as e:
        logger.error(f"E-Paper initial startup draw failed: {e}")

    while True:
        await asyncio.sleep(60) # Update every 1 minute
        
        try:
            if shared_state.get('pause_eink', False):
                continue
            total_count, captured_count = await db.get_stats()
            logger.info(f"Updating E-Paper display (periodic 1 minute update). Total: {total_count}, Captured: {captured_count}")
            await update_epaper_screen(db, total_count, captured_count, shared_state, picdir)
        except Exception as e:
            logger.error(f"E-Paper background updater loop error: {e}")
