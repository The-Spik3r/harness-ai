using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace Example.Billing
{
    /// <summary>
    /// Base type for every payment provider. A provider must override
    /// <see cref="ChargeAsync"/>; it may override <see cref="Supports"/> when
    /// it only handles a subset of currencies.
    /// </summary>
    public abstract class PaymentProcessor
    {
        protected PaymentProcessor(string name)
        {
            Name = name ?? throw new ArgumentNullException(nameof(name));
        }

        public string Name { get; }

        public virtual bool Supports(string currency) => true;

        public abstract Task<ChargeResult> ChargeAsync(
            decimal amount, string currency, CancellationToken cancellationToken);

        public override string ToString() => $"PaymentProcessor({Name})";
    }

    public sealed class CardProcessor : PaymentProcessor
    {
        private static readonly HashSet<string> Currencies =
            new(StringComparer.OrdinalIgnoreCase) { "USD", "EUR", "GBP" };

        private readonly ICardGateway _gateway;

        public CardProcessor(ICardGateway gateway) : base("card")
        {
            _gateway = gateway;
        }

        public override bool Supports(string currency) => Currencies.Contains(currency);

        public override async Task<ChargeResult> ChargeAsync(
            decimal amount, string currency, CancellationToken cancellationToken)
        {
            if (amount <= 0m)
            {
                return ChargeResult.Rejected("amount must be positive");
            }

            if (!Supports(currency))
            {
                return ChargeResult.Rejected($"unsupported currency {currency}");
            }

            var authorization = await _gateway
                .AuthorizeAsync(amount, currency, cancellationToken)
                .ConfigureAwait(false);

            return authorization.Approved
                ? ChargeResult.Accepted(authorization.Reference)
                : ChargeResult.Rejected(authorization.Reason);
        }

        public override string ToString() => $"CardProcessor({Currencies.Count} currencies)";

        public override bool Equals(object? obj) =>
            obj is CardProcessor other && ReferenceEquals(_gateway, other._gateway);

        public override int GetHashCode() => _gateway.GetHashCode();
    }

    public readonly record struct ChargeResult(bool Ok, string Detail)
    {
        public static ChargeResult Accepted(string reference) => new(true, reference);

        public static ChargeResult Rejected(string reason) => new(false, reason);
    }
}
