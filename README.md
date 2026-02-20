def basket_watcher():
    global lot_index, last_sl_time, last_pnl_log_time

    while True:
        pos = get_positions()
        pnl = floating_pnl()
        now = time.time()

        if pos and now - last_pnl_log_time >= PNL_LOG_INTERVAL:
            log.info(
                f"BASKET STATUS | PnL={pnl:.2f} | POS={len(pos)} | LOT={total_buy_volume():.2f}"
            )
            last_pnl_log_time = now

        if pos and pnl >= MIN_BASKET_PROFIT:
            log.info(f"BASKET TP HIT | PnL={pnl:.2f}")
            close_all()
            lot_index = 0
            time.sleep(1)
            continue

        if pnl <= FLOATING_LOSS_LIMIT and now - last_sl_time > SL_COOLDOWN_SEC:
            log.critical(f"BASKET SL HIT | PnL={pnl:.2f}")
            close_all()
            lot_index = 0
            last_sl_time = now
            time.sleep(1)
            continue

        time.sleep(0.05)
