// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

using Confluent.Kafka;
using Microsoft.Extensions.Logging;
using Oteldemo;
using Microsoft.EntityFrameworkCore;
using System.Diagnostics;

namespace Accounting;

internal class DBContext : DbContext
{
    public DbSet<OrderEntity> Orders { get; set; }
    public DbSet<OrderItemEntity> CartItems { get; set; }
    public DbSet<ShippingEntity> Shipping { get; set; }

    protected override void OnConfiguring(DbContextOptionsBuilder optionsBuilder)
    {
        var connectionString = Environment.GetEnvironmentVariable("DB_CONNECTION_STRING");

        optionsBuilder.UseNpgsql(connectionString).UseSnakeCaseNamingConvention();
    }
}


internal class Consumer : IDisposable
{
    private const string TopicName = "orders";

    private ILogger _logger;
    private IConsumer<string, byte[]> _consumer;
    private bool _isListening;
    private readonly string? _dbConnectionString;
    private static readonly ActivitySource MyActivitySource = new("Accounting.Consumer");

    public Consumer(ILogger<Consumer> logger)
    {
        _logger = logger;

        var servers = Environment.GetEnvironmentVariable("KAFKA_ADDR")
            ?? throw new InvalidOperationException("The KAFKA_ADDR environment variable is not set.");

        _consumer = BuildConsumer(servers);
        _consumer.Subscribe(TopicName);

       if (_logger.IsEnabled(LogLevel.Information))
       {
           _logger.LogInformation("Connecting to Kafka: {servers}", servers);
       }

        _dbConnectionString = Environment.GetEnvironmentVariable("DB_CONNECTION_STRING");
    }

    public void StartListening()
    {
        _isListening = true;

        try
        {
            while (_isListening)
            {
                try
                {
                    var consumeResult = _consumer.Consume();

                    // Extract trace context from Kafka headers and create a span link
                    var links = new List<ActivityLink>();
                    var baggage = new List<KeyValuePair<string, string?>>();
                    var traceparent = GetHeaderValue(consumeResult.Message.Headers, "traceparent");
                    var tracestate = GetHeaderValue(consumeResult.Message.Headers, "tracestate");

                    if (traceparent != null && ActivityContext.TryParse(traceparent, tracestate, out var producerContext))
                    {
                        links.Add(new ActivityLink(producerContext));
                    }

                    // Extract baggage from Kafka headers
                    var baggageHeader = GetHeaderValue(consumeResult.Message.Headers, "baggage");
                    if (baggageHeader != null)
                    {
                        foreach (var entry in baggageHeader.Split(','))
                        {
                            var parts = entry.Trim().Split('=', 2);
                            if (parts.Length == 2)
                            {
                                baggage.Add(new KeyValuePair<string, string?>(
                                    Uri.UnescapeDataString(parts[0]),
                                    Uri.UnescapeDataString(parts[1])));
                            }
                        }
                    }

                    using var activity = MyActivitySource.StartActivity(
                        "orders process",
                        ActivityKind.Consumer,
                        parentContext: default,
                        links: links,
                        tags: new[]
                        {
                            new KeyValuePair<string, object?>("messaging.system", "kafka"),
                            new KeyValuePair<string, object?>("messaging.destination.name", TopicName),
                            new KeyValuePair<string, object?>("messaging.operation", "process"),
                        });

                    // Add baggage entries as both baggage and span attributes
                    if (activity != null)
                    {
                        foreach (var entry in baggage)
                        {
                            activity.AddBaggage(entry.Key, entry.Value);
                            activity.SetTag(entry.Key, entry.Value);
                        }
                    }

                    ProcessMessage(consumeResult.Message);
                }
                catch (ConsumeException e)
                {
                    if (_logger.IsEnabled(LogLevel.Error))
                    {
                        _logger.LogError(e, "Consume error: {reason}", e.Error.Reason);
                    }
                }
            }
        }
        catch (OperationCanceledException)
        {
            _logger.LogInformation("Closing consumer");

            _consumer.Close();
        }
    }

    private static string? GetHeaderValue(Headers? headers, string key)
    {
        if (headers == null) return null;
        try
        {
            var header = headers.GetLastBytes(key);
            return header != null ? System.Text.Encoding.UTF8.GetString(header) : null;
        }
        catch (KeyNotFoundException)
        {
            return null;
        }
    }

    private void ProcessMessage(Message<string, byte[]> message)
    {
        try
        {
            var order = OrderResult.Parser.ParseFrom(message.Value);
            Log.OrderReceivedMessage(_logger, order);

            if (_dbConnectionString == null)
            {
                return;
            }

            using var dbContext = new DBContext();
            var orderEntity = new OrderEntity
            {
                Id = order.OrderId
            };
            dbContext.Add(orderEntity);
            foreach (var item in order.Items)
            {
                var orderItem = new OrderItemEntity
                {
                    ItemCostCurrencyCode = item.Cost.CurrencyCode,
                    ItemCostUnits = item.Cost.Units,
                    ItemCostNanos = item.Cost.Nanos,
                    ProductId = item.Item.ProductId,
                    Quantity = item.Item.Quantity,
                    OrderId = order.OrderId
                };

                dbContext.Add(orderItem);
            }

            var shipping = new ShippingEntity
            {
                ShippingTrackingId = order.ShippingTrackingId,
                ShippingCostCurrencyCode = order.ShippingCost.CurrencyCode,
                ShippingCostUnits = order.ShippingCost.Units,
                ShippingCostNanos = order.ShippingCost.Nanos,
                StreetAddress = order.ShippingAddress.StreetAddress,
                City = order.ShippingAddress.City,
                State = order.ShippingAddress.State,
                Country = order.ShippingAddress.Country,
                ZipCode = order.ShippingAddress.ZipCode,
                OrderId = order.OrderId
            };
            dbContext.Add(shipping);
            dbContext.SaveChanges();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Order parsing failed:");
        }
    }

    private static IConsumer<string, byte[]> BuildConsumer(string servers)
    {
        var conf = new ConsumerConfig
        {
            GroupId = $"accounting",
            BootstrapServers = servers,
            // https://github.com/confluentinc/confluent-kafka-dotnet/tree/07de95ed647af80a0db39ce6a8891a630423b952#basic-consumer-example
            AutoOffsetReset = AutoOffsetReset.Earliest,
            EnableAutoCommit = true
        };

        return new ConsumerBuilder<string, byte[]>(conf)
            .Build();
    }

    public void Dispose()
    {
        _isListening = false;
        _consumer?.Dispose();
    }
}
