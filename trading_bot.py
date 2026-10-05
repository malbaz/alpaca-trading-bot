def manage_open_positions(trading_client):
    try:
        positions = trading_client.get_all_positions()
        if not positions:
            print("لا توجد مراكز مفتوحة حالياً للبيع.")
            return

        for pos in positions:
            symbol = pos.symbol
            qty = float(pos.qty)
            entry_price = float(pos.avg_entry_price)
            current_price = float(pos.current_price)  # اعتماد سعر Alpaca المباشر واللحظي

            change_pct = (current_price - entry_price) / entry_price
            print(f"فحص {symbol}: سعر الدخول ${entry_price:.2f} | اللحظي من Alpaca ${current_price:.2f} | التغير: {change_pct*100:.2f}%")

            if change_pct >= QUICK_TAKE_PROFIT_PCT or change_pct <= -STOP_LOSS_PCT:
                reason = f"وقف خسارة (-{STOP_LOSS_PCT*100:.1f}%)" if change_pct <= -STOP_LOSS_PCT else f"جني أرباح (+{QUICK_TAKE_PROFIT_PCT*100:.1f}%)"
                print(f"🚨 تفعيل الخروج الآلي لـ {symbol}: {reason} [السعر: ${current_price:.2f}]")

                cancel_open_orders_for_symbol(trading_client, symbol)

                sell_limit_price = round(current_price * 0.990, 2) if change_pct <= -STOP_LOSS_PCT else round(current_price, 2)

                exit_order = LimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                    limit_price=sell_limit_price,
                    extended_hours=True
                )
                trading_client.submit_order(exit_order)
                print(f"✅ تم إرسال أمر البيع لـ {symbol} بسعر ${sell_limit_price}")

    except Exception as e:
        print(f"خطأ أثناء إدارة الصفقات المفتوحة: {e}")
