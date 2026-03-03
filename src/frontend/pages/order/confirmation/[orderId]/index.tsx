// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import { NextPage } from 'next';
import Head from 'next/head';
import Link from 'next/link';
import { useRouter } from 'next/router';
import { useEffect } from 'react';
import Ad from '../../../../components/Ad';
import Button from '../../../../components/Button';
import CheckoutItem from '../../../../components/CheckoutItem';
import Layout from '../../../../components/Layout';
import Recommendations from '../../../../components/Recommendations';
import AdProvider from '../../../../providers/Ad.provider';
import SessionGateway from '../../../../gateways/Session.gateway';
import { useCurrency } from '../../../../providers/Currency.provider';
import * as S from '../../../../styles/Checkout.styled';
import { IProductCheckout } from '../../../../types/Cart';

const { userId } = SessionGateway.getSession();

const Checkout: NextPage = () => {
  const { query } = useRouter();
  const { selectedCurrency } = useCurrency();
  const { items = [], shippingAddress, orderId, shippingCost } = JSON.parse((query.order || '{}') as string) as IProductCheckout;

  // Create a custom span for order confirmation
  useEffect(() => {
    if (orderId && typeof window !== 'undefined') {
      // Use the tracer from window if available (initialized in _document.tsx)
      if (typeof (window as any).tracer !== 'undefined') {
        const tracer = (window as any).tracer;
        const span = tracer.startSpan('order.confirmed', {
          attributes: {
            'app.order.id': orderId,
            'app.user.id': userId,
            'app.user.currency': selectedCurrency,
            'app.order.items.count': items.length,
            'app.order.total_items': items.reduce((sum, item) => sum + item.item.quantity, 0),
            'app.shipping.amount': shippingCost?.units || 0,
          },
        });

        console.log('Order confirmation span created:', {
          orderId,
          userId,
          currency: selectedCurrency,
          itemsCount: items.length,
          totalItems: items.reduce((sum, item) => sum + item.item.quantity, 0),
          shippingAmount: shippingCost?.units || 0,
        });

        // End the span immediately as this is just a marker
        span.end();
      }
    }
  }, [orderId, items, selectedCurrency, shippingCost]);

  return (
    <AdProvider
      productIds={items.map(({ item }) => item?.productId || '')}
      contextKeys={[...new Set(items.flatMap(({ item }) => item.product.categories))]}
    >
      <Head>
        <title>Otel Demo - Order Confirmation</title>
      </Head>
      <Layout>
        <S.Checkout>
          <S.Container>
            <S.Title>Your order is complete!</S.Title>
            <S.Subtitle>We&apos;ve sent you a confirmation email.</S.Subtitle>

            <S.ItemList>
              {items.map(checkoutItem => (
                <CheckoutItem
                  key={checkoutItem.item.productId}
                  checkoutItem={checkoutItem}
                  address={shippingAddress}
                />
              ))}
            </S.ItemList>

            <S.ButtonContainer>
              <Link href="/">
                <Button id="btn-order-confirmation-continue-shopping" type="submit">Continue Shopping</Button>
              </Link>
            </S.ButtonContainer>
          </S.Container>
          <Recommendations />
        </S.Checkout>
        <Ad />
      </Layout>
    </AdProvider>
  );
};

export default Checkout;
