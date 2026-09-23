package com.example.orders;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Settles pending orders on a schedule.
 *
 * <p>Runs as a {@link Runnable} on the settlement executor. Subclasses may
 * override {@link #shouldSettle(Order)} to add a region-specific hold, but
 * must call the parent implementation first.
 */
public class OrderService implements Runnable, AutoCloseable {

    private final OrderRepository repository;
    private final PaymentGateway gateway;
    private final Clock clock;
    private final AtomicBoolean closed = new AtomicBoolean(false);

    public OrderService(OrderRepository repository, PaymentGateway gateway, Clock clock) {
        this.repository = Objects.requireNonNull(repository, "repository");
        this.gateway = Objects.requireNonNull(gateway, "gateway");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    @Override
    public void run() {
        if (closed.get()) {
            return;
        }
        List<Order> pending = repository.findPending();
        for (Order order : pending) {
            if (shouldSettle(order)) {
                settle(order);
            }
        }
    }

    protected boolean shouldSettle(Order order) {
        return order.total().compareTo(BigDecimal.ZERO) > 0
                && order.placedAt().isBefore(Instant.now(clock).minusSeconds(300));
    }

    private void settle(Order order) {
        Optional<String> receipt = gateway.capture(order.id(), order.total());
        receipt.ifPresentOrElse(
                id -> repository.markSettled(order.id(), id),
                () -> repository.markFailed(order.id(), "capture declined"));
    }

    @Override
    public void close() {
        closed.set(true);
    }

    @Override
    public String toString() {
        return "OrderService[closed=" + closed.get() + "]";
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof OrderService)) {
            return false;
        }
        OrderService that = (OrderService) other;
        return repository.equals(that.repository) && gateway.equals(that.gateway);
    }

    @Override
    public int hashCode() {
        return Objects.hash(repository, gateway);
    }

    /** A hold for orders shipped to regions with a cooling-off period. */
    static final class RegionalOrderService extends OrderService {

        RegionalOrderService(OrderRepository repository, PaymentGateway gateway, Clock clock) {
            super(repository, gateway, clock);
        }

        @Override
        protected boolean shouldSettle(Order order) {
            return super.shouldSettle(order) && !order.region().equals("EU-HOLD");
        }
    }
}
