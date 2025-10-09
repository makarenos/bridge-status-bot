"""
Main bridge monitoring service
Checks bridge health via multiple methods (APIs, subgraphs, on-chain data)
"""

import time
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select

from app.models.bridge import Bridge, BridgeStatus, Incident
from app.services.status_analyzer import determine_status, calculate_severity
from app.core.redis import RedisClient
from app.utils.logger import logger


class BridgeMonitor:
    """
    Core monitoring class for bridge health checks

    Uses multiple methods to check bridge health:
    - TheGraph subgraphs (for on-chain data)
    - Public APIs (where available)
    - RPC calls (as fallback)
    - Website availability checks
    """

    # TheGraph subgraph endpoints
    SUBGRAPHS = {
        "Stargate": "https://api.thegraph.com/subgraphs/name/stargate-protocol/stargate-ethereum",
        "Hop Protocol": "https://api.thegraph.com/subgraphs/name/hop-protocol/hop-mainnet",
    }

    # Working API endpoints
    APIS = {
        "Hop Protocol": "https://api.hop.exchange/v1/quote",
        "Stargate": "https://stargate.finance/api/v1/tokens",
    }

    def __init__(
        self,
        session_maker: async_sessionmaker,
        redis_client: RedisClient,
        notification_service=None,
        websocket_manager=None
    ):
        # store session maker instead of a single session
        # this way each check can create its own session
        self.session_maker = session_maker
        self.redis = redis_client
        self.notification_service = notification_service
        self.websocket_manager = websocket_manager
        self.http_session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        """Initialize HTTP session for connection reuse"""
        if not self.http_session:
            timeout = aiohttp.ClientTimeout(total=60, connect=10)
            self.http_session = aiohttp.ClientSession(timeout=timeout)

    async def close(self):
        """Close HTTP session on cleanup"""
        if self.http_session:
            await self.http_session.close()
            self.http_session = None

    async def check_bridge_health(self, bridge: Bridge) -> BridgeStatus:
        """
        Main health check function - tries multiple methods to verify bridge health

        Creates its own DB session to avoid conflicts when running in parallel

        Priority:
        1. Bridge-specific API/subgraph (most reliable)
        2. Generic health checks
        3. Fallback to simple availability check
        """
        start_time = time.time()
        logger.info(f"Checking bridge: {bridge.name}")

        # create a new session for this check to avoid concurrent access issues
        async with self.session_maker() as db:
            try:
                # use bridge-specific check method
                if bridge.name == "Stargate":
                    result = await self._check_stargate()
                elif bridge.name == "Hop Protocol":
                    result = await self._check_hop_protocol()
                elif bridge.name == "Arbitrum Bridge":
                    result = await self._check_arbitrum()
                elif bridge.name == "Optimism Bridge":
                    result = await self._check_optimism()
                elif bridge.name == "Polygon Bridge":
                    result = await self._check_polygon()
                else:
                    # fallback - just check if endpoint responds
                    result = await self._check_generic(bridge.api_endpoint)

                response_time = int((time.time() - start_time) * 1000)

                # determine status based on results
                status = determine_status(
                    response_time=response_time,
                    http_code=result.get('http_code', 200),
                    bridge_specific_checks=result
                )

                # save to DB
                bridge_status = await self._save_status(
                    db=db,
                    bridge_id=bridge.id,
                    status=status,
                    response_time=response_time,
                    extra_data=result
                )

                # check for status changes
                await self._check_status_change(db, bridge, status, response_time)

                logger.info(f"{bridge.name}: {status} ({response_time}ms)")
                return bridge_status

            except asyncio.TimeoutError:
                logger.warning(f"{bridge.name}: Timeout")
                return await self._handle_timeout(db, bridge)

            except Exception as e:
                logger.error(f"{bridge.name}: Error - {e}", exc_info=True)
                return await self._handle_error(db, bridge, str(e))

    async def _check_stargate(self) -> Dict[str, Any]:
        """
        Check Stargate bridge via their API and subgraph

        Method: Query their tokens API to see if bridge is operational
        """
        result = {
            'critical_failure': False,
            'degraded_service': False,
            'method': 'api_check'
        }

        try:
            # try their tokens API
            async with self.http_session.get(
                self.APIS["Stargate"],
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    # if we get tokens data, bridge APIs are working
                    result['tokens_available'] = len(data.get('tokens', []))
                    result['http_code'] = 200
                else:
                    result['degraded_service'] = True
                    result['http_code'] = response.status

        except Exception as e:
            logger.warning(f"Stargate API check failed: {e}")
            result['degraded_service'] = True
            result['http_code'] = 500

        return result

    async def _check_hop_protocol(self) -> Dict[str, Any]:
        """
        Check Hop Protocol via their quote API

        Method: Try to get a quote - if it works, bridge is operational
        Note: Hop API is intentionally slow (15-30s) - it's designed for
              real transfers, not quick health checks. This is NORMAL for Hop.
        """
        result = {
            'critical_failure': False,
            'degraded_service': False,  # we'll mark as degraded on timeout
            'method': 'quote_api'
        }

        try:
            # try to get a quote for a small USDC transfer
            params = {
                'amount': '1000000',  # 1 USDC
                'token': 'USDC',
                'fromChain': 'ethereum',
                'toChain': 'arbitrum',
                'slippage': '0.5'
            }

            # Hop API is VERY slow - use 40s timeout
            # 30s+ response time = WARNING (still working, just slow)
            async with self.http_session.get(
                    self.APIS["Hop Protocol"],
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=40)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    # if we get a valid quote, bridge is working
                    result['quote_available'] = 'estimatedRecieved' in data
                    result['bonder_fee'] = data.get('bonderFee', 0)
                    result['http_code'] = 200
                else:
                    result['degraded_service'] = True
                    result['http_code'] = response.status

        except asyncio.TimeoutError:
            # Timeout after 40s - mark as degraded but not critical
            # This makes status = WARNING instead of DOWN
            logger.warning(
                "Hop API timeout after 40s - API is very slow but likely operational")
            result['degraded_service'] = True  # this triggers WARNING status
            result['http_code'] = 200  # not a real error, just slow

        except Exception as e:
            logger.warning(f"Hop API check failed: {e}")
            result['degraded_service'] = True
            result['http_code'] = 500

        return result

    async def _check_arbitrum(self) -> Dict[str, Any]:
        """
        Check Arbitrum bridge

        Method: Check their official bridge portal availability
        Note: Arbitrum doesn't have a public health API, so we check portal + could add RPC calls
        """
        result = {
            'critical_failure': False,
            'degraded_service': False,
            'method': 'portal_check'
        }

        try:
            # check if bridge portal is accessible
            async with self.http_session.get(
                "https://bridge.arbitrum.io",
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                result['http_code'] = response.status
                if response.status != 200:
                    result['degraded_service'] = True

                # TODO: could add RPC call to check bridge contract state
                # via web3.py and arbitrum RPC endpoint

        except Exception as e:
            logger.warning(f"Arbitrum check failed: {e}")
            result['critical_failure'] = True
            result['http_code'] = 500

        return result

    async def _check_optimism(self) -> Dict[str, Any]:
        """
        Check Optimism bridge

        Method: Check official gateway availability
        """
        result = {
            'critical_failure': False,
            'degraded_service': False,
            'method': 'gateway_check'
        }

        try:
            async with self.http_session.get(
                "https://app.optimism.io/bridge",
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                result['http_code'] = response.status
                if response.status != 200:
                    result['degraded_service'] = True

        except Exception as e:
            logger.warning(f"Optimism check failed: {e}")
            result['critical_failure'] = True
            result['http_code'] = 500

        return result

    async def _check_polygon(self) -> Dict[str, Any]:
        """
        Check Polygon bridge

        Method: Check wallet bridge portal
        """
        result = {
            'critical_failure': False,
            'degraded_service': False,
            'method': 'portal_check'
        }

        try:
            async with self.http_session.get(
                "https://wallet.polygon.technology/polygon/bridge",
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                result['http_code'] = response.status
                if response.status != 200:
                    result['degraded_service'] = True

        except Exception as e:
            logger.warning(f"Polygon check failed: {e}")
            result['critical_failure'] = True
            result['http_code'] = 500

        return result

    async def _check_generic(self, endpoint: str) -> Dict[str, Any]:
        """
        Generic health check - just verify endpoint is accessible
        Used as fallback when no specific method is available
        """
        result = {
            'critical_failure': False,
            'degraded_service': False,
            'method': 'generic_http'
        }

        try:
            async with self.http_session.get(
                endpoint,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                result['http_code'] = response.status
                if response.status >= 500:
                    result['critical_failure'] = True
                elif response.status >= 400:
                    result['degraded_service'] = True

        except Exception as e:
            logger.warning(f"Generic check failed for {endpoint}: {e}")
            result['critical_failure'] = True
            result['http_code'] = 500

        return result

    async def _query_subgraph(self, bridge_name: str, query: str) -> Optional[dict]:
        """
        Query TheGraph subgraph for a bridge

        Useful for getting on-chain data like recent transfers, liquidity, etc.
        """
        subgraph_url = self.SUBGRAPHS.get(bridge_name)
        if not subgraph_url:
            return None

        try:
            async with self.http_session.post(
                subgraph_url,
                json={'query': query},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            logger.warning(f"Subgraph query failed for {bridge_name}: {e}")

        return None

    async def _save_status(
        self,
        db: AsyncSession,
        bridge_id: int,
        status: str,
        response_time: Optional[int],
        extra_data: dict,
        error_message: Optional[str] = None
    ) -> BridgeStatus:
        """Save status check result to DB"""
        bridge_status = BridgeStatus(
            bridge_id=bridge_id,
            status=status,
            response_time=response_time,
            error_message=error_message,
            extra_data=extra_data,
            checked_at=datetime.now(timezone.utc)
        )

        db.add(bridge_status)
        await db.commit()
        await db.refresh(bridge_status)

        return bridge_status

    async def _check_status_change(
        self,
        db: AsyncSession,
        bridge: Bridge,
        new_status: str,
        response_time: Optional[int] = None
    ):
        """Check if bridge status changed and trigger alerts if needed"""
        cache_key = f"bridge:{bridge.id}:status"
        cached_status = await self.redis.get(cache_key)

        if cached_status and cached_status != new_status:
            logger.info(
                f"Status changed for {bridge.name}: {cached_status} -> {new_status}"
            )
            await self._handle_status_change(
                db, bridge, cached_status, new_status, response_time
            )

        # update cache
        await self.redis.set(cache_key, new_status, ex=7200)

    async def _handle_status_change(
        self,
        db: AsyncSession,
        bridge: Bridge,
        old_status: str,
        new_status: str,
        response_time: Optional[int] = None
    ):
        """Handle status changes - create incidents and send alerts"""
        severity = calculate_severity(new_status, old_status)

        # broadcast via WebSocket
        if self.websocket_manager:
            try:
                await self.websocket_manager.broadcast_bridge_status(
                    bridge_id=bridge.id,
                    bridge_name=bridge.name,
                    status=new_status,
                    response_time=response_time,
                    extra_data={'old_status': old_status, 'severity': severity}
                )
            except Exception as e:
                logger.error(f"Failed to broadcast WebSocket update: {e}")

        if new_status in ["DOWN", "WARNING", "SLOW"]:
            # create incident
            incident = Incident(
                bridge_id=bridge.id,
                title=f"{bridge.name} is {new_status}",
                description=f"Status changed from {old_status} to {new_status}",
                status="ACTIVE",
                severity=severity,
                started_at=datetime.now(timezone.utc),
                extra_data={'previous_status': old_status}
            )
            db.add(incident)
            await db.commit()

            logger.warning(f"Created incident for {bridge.name}: {severity} severity")

            # send alert to users
            if self.notification_service:
                try:
                    await self.notification_service.send_bridge_alert(
                        bridge=bridge,
                        new_status=new_status,
                        old_status=old_status,
                        severity=severity,
                        response_time=response_time
                    )
                except Exception as e:
                    logger.error(f"Failed to send alert: {e}", exc_info=True)

        elif new_status == "UP" and old_status in ["DOWN", "WARNING", "SLOW"]:
            # resolve incidents
            result = await db.execute(
                select(Incident).where(
                    Incident.bridge_id == bridge.id,
                    Incident.status == "ACTIVE"
                )
            )
            active_incidents = result.scalars().all()

            downtime_minutes = 0
            if active_incidents:
                first_incident = min(active_incidents, key=lambda i: i.started_at)
                downtime = datetime.now(timezone.utc) - first_incident.started_at
                downtime_minutes = int(downtime.total_seconds() / 60)

            for incident in active_incidents:
                incident.status = "RESOLVED"
                incident.resolved_at = datetime.now(timezone.utc)

            await db.commit()
            logger.info(f"Resolved incidents for {bridge.name}")

            # send recovery alert
            if self.notification_service and downtime_minutes > 0:
                try:
                    await self.notification_service.send_recovery_alert(
                        bridge=bridge,
                        downtime_minutes=downtime_minutes
                    )
                except Exception as e:
                    logger.error(f"Failed to send recovery alert: {e}", exc_info=True)

    async def _handle_timeout(self, db: AsyncSession, bridge: Bridge) -> BridgeStatus:
        """Handle request timeout"""
        return await self._save_status(
            db=db,
            bridge_id=bridge.id,
            status="DOWN",
            response_time=None,
            extra_data={'critical_failure': True, 'error': 'timeout'},
            error_message="Request timeout"
        )

    async def _handle_error(self, db: AsyncSession, bridge: Bridge, error: str) -> BridgeStatus:
        """Handle general errors"""
        return await self._save_status(
            db=db,
            bridge_id=bridge.id,
            status="DOWN",
            response_time=None,
            extra_data={'critical_failure': True, 'error': error},
            error_message=error
        )

    async def check_all_bridges(self):
        """
        Check all active bridges in parallel

        Each check gets its own DB session to avoid concurrent access issues
        This is safe because we're using session_maker instead of a shared session
        """
        # get list of bridges to check (using a temporary session)
        async with self.session_maker() as db:
            result = await db.execute(
                select(Bridge).where(Bridge.is_active == True)
            )
            bridges = result.scalars().all()

        logger.info(f"Checking {len(bridges)} bridges...")

        # check all bridges in parallel - each will create its own session
        tasks = [self.check_bridge_health(bridge) for bridge in bridges]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # log summary
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        logger.info(
            f"Bridge check completed: {success_count}/{len(bridges)} successful"
        )

        return results