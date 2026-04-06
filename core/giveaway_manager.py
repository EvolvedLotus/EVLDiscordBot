import logging
import random
import asyncio
from datetime import datetime, timezone, timedelta
import discord

from core.audit_manager import AuditEventType

logger = logging.getLogger(__name__)

class GiveawayManager:
    """Manages the full lifecycle of giveaways."""

    def __init__(self, data_manager=None, transaction_manager=None, shop_manager=None):
        self.data_manager = data_manager
        self.transaction_manager = transaction_manager
        self.shop_manager = shop_manager
        
        self.sse_manager = None
        self.cache_manager = None
        self.bot = None

    def set_data_manager(self, dm):
        self.data_manager = dm
    def set_transaction_manager(self, tm):
        self.transaction_manager = tm
    def set_shop_manager(self, sm):
        self.shop_manager = sm
    def set_sse_manager(self, sm):
        self.sse_manager = sm
    def set_cache_manager(self, cm):
        self.cache_manager = cm
    def set_bot(self, bot):
        self.bot = bot

    def create_giveaway(self, guild_id: str, creator_id: str, config: dict) -> dict:
        """Create a new giveaway and optionally schedule it."""
        try:
            # Validate input rules
            prize_source = config.get('prize_source', 'custom')
            prize_name = config.get('prize_name', '')
            if prize_source == 'custom' and (not prize_name or len(prize_name) > 100):
                raise ValueError("prize_name must be between 1 and 100 characters")
            
            prize_description = config.get('prize_description', '')
            if prize_description and len(prize_description) > 500:
                raise ValueError("prize_description max 500 characters")
                
            custom_message = config.get('custom_message', '')
            if custom_message and len(custom_message) > 500:
                raise ValueError("custom_message max 500 characters")
                
            winner_count = int(config.get('winner_count', 1))
            if winner_count < 1 or winner_count > 20:
                raise ValueError("winner_count must be between 1 and 20")

            ends_at_str = config.get('ends_at')
            if not ends_at_str:
                raise ValueError("ends_at is required")
                
            ends_at = datetime.fromisoformat(ends_at_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            if ends_at <= now + timedelta(minutes=1):
                raise ValueError("ends_at must be at least 1 minute from now")
            if ends_at > now + timedelta(days=30):
                raise ValueError("duration max 30 days")

            entry_mode = config.get('entry_mode')
            if entry_mode not in ('open', 'role_restricted', 'raffle'):
                raise ValueError("Invalid entry_mode")

            raffle_cost = config.get('raffle_cost')
            raffle_max_tickets_per_user = config.get('raffle_max_tickets_per_user', 10)
            required_role_ids = config.get('required_role_ids', [])

            if entry_mode == 'raffle':
                if not raffle_cost or int(raffle_cost) <= 0:
                    raise ValueError("raffle_cost must be > 0 when mode is raffle")
                if int(raffle_max_tickets_per_user) < 1:
                    raise ValueError("raffle_max_tickets_per_user must be >= 1")
                raffle_cost = int(raffle_cost)
                raffle_max_tickets_per_user = int(raffle_max_tickets_per_user)
            elif entry_mode == 'role_restricted':
                if not required_role_ids:
                    raise ValueError("required_role_ids must be non-empty when mode is role_restricted")

            shop_item_id = config.get('shop_item_id')
            prize_image_url = config.get('prize_image_url')

            if prize_source == 'shop_item':
                if not shop_item_id:
                    raise ValueError("shop_item_id is required when prize_source is shop_item")
                # Fetch shop item and validate
                try:
                    currency_data = self.data_manager.load_guild_data(str(guild_id), 'currency')
                    shop_item = currency_data.get('shop_items', {}).get(shop_item_id)
                    if not shop_item:
                        raise ValueError("Shop item not found")
                    # Assuming we map properties correctly
                    prize_name = shop_item.get('name', prize_name)
                    prize_description = shop_item.get('description', prize_description)
                    prize_image_url = shop_item.get('image_url', prize_image_url)
                    
                    if not prize_name or len(prize_name) > 100:
                         raise ValueError("Fetched shop item name must be between 1 and 100 characters")
                except Exception as e:
                    if isinstance(e, ValueError): raise e
                    raise ValueError(f"Failed to fetch shop item: {e}")

            start_at_str = config.get('start_at')
            status = 'active'
            if start_at_str:
                start_at = datetime.fromisoformat(start_at_str.replace('Z', '+00:00'))
                if start_at > now:
                    status = 'scheduled'

            # Channel validation
            channel_id = str(config.get('channel_id'))
            if self.bot:
                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    raise ValueError("channel_id must be a valid text channel the bot can see")

            giveaway_data = {
                'guild_id': str(guild_id),
                'created_by': str(creator_id),
                'prize_source': prize_source,
                'shop_item_id': shop_item_id if prize_source == 'shop_item' else None,
                'prize_name': prize_name,
                'prize_description': prize_description,
                'prize_image_url': prize_image_url,
                'winner_count': winner_count,
                'entry_mode': entry_mode,
                'required_role_ids': required_role_ids,
                'raffle_cost': raffle_cost if entry_mode == 'raffle' else None,
                'raffle_max_tickets_per_user': raffle_max_tickets_per_user if entry_mode == 'raffle' else None,
                'tag_role_id': str(config.get('tag_role_id')) if config.get('tag_role_id') else None,
                'custom_message': custom_message,
                'channel_id': channel_id,
                'status': status,
                'start_at': start_at_str,
                'ends_at': ends_at.isoformat(),
            }

            result = self.data_manager.admin_client.table('giveaways').insert(giveaway_data).execute()
            if not result.data:
                raise Exception("Failed to insert giveaway")
                
            created = result.data[0]
            
            # Log audit
            if hasattr(self.data_manager, 'bot') and hasattr(self.data_manager.bot, 'audit_manager') and self.data_manager.bot.audit_manager:
                 self.data_manager.bot.audit_manager.log_event(
                     AuditEventType.GIVEAWAY_CREATED,
                     guild_id=int(guild_id),
                     user_id=None,
                     moderator_id=int(creator_id),
                     details={'giveaway_id': created['id'], 'prize_name': prize_name}
                 )

            # Broadcast SSE
            if self.sse_manager:
                self.sse_manager.broadcast_event('giveaway_created', {
                    'giveaway_id': created['id'],
                    'guild_id': str(guild_id),
                    'prize_name': prize_name,
                    'status': status,
                    'ends_at': created['ends_at']
                }, target_guild=str(guild_id))

            return created

        except Exception as e:
            logger.error(f"Error creating giveaway: {e}")
            raise e

    async def post_giveaway_embed(self, giveaway_id: str) -> tuple:
        """Posts the embed for a giveaway in its channel."""
        try:
            giveaway = self.get_giveaway(giveaway_id, None)
            if not giveaway:
                raise ValueError("Giveaway not found")

            if not self.bot:
                logger.warning("Bot instance not set for GiveawayManager")
                return None, None

            channel = self.bot.get_channel(int(giveaway['channel_id']))
            if not channel:
                # Might be a mismatch or bot lacks permission
                raise Exception(f"Channel {giveaway['channel_id']} not found or inaccessible")

            content = ""
            if giveaway.get('custom_message'):
                content += giveaway['custom_message'] + "\n"
            if giveaway.get('tag_role_id'):
                content += f"<@&{giveaway['tag_role_id']}>"

            embed = self._build_live_embed(giveaway)
            
            # Use dynamic import to avoid circular dependency
            from cogs.giveaways import GiveawayEntryView
            view = GiveawayEntryView(giveaway_id=giveaway_id)

            message = await channel.send(content, embed=embed, view=view)

            # Save message_id
            self.data_manager.admin_client.table('giveaways').update({'message_id': str(message.id)}).eq('id', giveaway_id).execute()
            
            return giveaway['channel_id'], str(message.id)

        except Exception as e:
            logger.error(f"Error posting giveaway embed: {e}")
            
            # Set status back to scheduled with error if forbidden
            if isinstance(e, discord.Forbidden):
               self.data_manager.admin_client.table('giveaways').update({'status': 'scheduled', 'message_id': None}).eq('id', giveaway_id).execute()
               # Audit log the error
               try:
                   giveaway = self.get_giveaway(giveaway_id, None)
                   if hasattr(self.data_manager, 'bot') and hasattr(self.data_manager.bot, 'audit_manager') and self.data_manager.bot.audit_manager:
                       self.data_manager.bot.audit_manager.log_event(
                           AuditEventType.GIVEAWAY_ERROR,
                           guild_id=int(giveaway['guild_id']),
                           user_id=None,
                           moderator_id=None,
                           details={'giveaway_id': giveaway_id, 'error': 'Missing permissions to post in channel'}
                       )
               except: pass
               
            return None, None

    def enter_giveaway(self, giveaway_id: str, guild_id: str, user_id: str, tickets: int = 1) -> dict:
        """User enters a giveaway."""
        try:
            giveaway = self.get_giveaway(giveaway_id, guild_id)
            if not giveaway:
                raise ValueError("Giveaway not found")
                
            if giveaway['status'] != 'active':
                raise ValueError("Giveaway is not active")
                
            if giveaway['created_by'] == user_id:
                raise ValueError("You cannot enter your own giveaway")

            ends_at = datetime.fromisoformat(giveaway['ends_at'].replace('Z', '+00:00'))
            if ends_at <= datetime.now(timezone.utc):
                raise ValueError("This giveaway has ended")

            entry_mode = giveaway['entry_mode']
            
            existing_entry = self.get_user_entry(giveaway_id, user_id)
            
            amount_spent = 0
            
            if entry_mode == 'role_restricted':
                # Role validation happens in discord UI view (member.roles)
                # But as a fallback check, handled outside or strictly trusted calling layer
                pass
                
            elif entry_mode == 'raffle':
                if tickets < 1:
                    raise ValueError("Must purchase at least 1 ticket")
                
                # Use atomic Postgres RPC to deduct balance and insert tickets in one locked transaction
                rpc_res = self.data_manager.admin_client.rpc('enter_raffle_giveaway', {
                    'p_giveaway_id': giveaway_id,
                    'p_guild_id': str(guild_id),
                    'p_user_id': str(user_id),
                    'p_tickets': tickets,
                    'p_raffle_cost': giveaway.get('raffle_cost', 0),
                    'p_max_tickets': giveaway.get('raffle_max_tickets_per_user', 10),
                    'p_reason': f"Giveaway raffle entry ({tickets} tickets)",
                    'p_transaction_type': 'giveaway_raffle'
                }).execute()
                
                if not rpc_res.data or not rpc_res.data.get('success'):
                    err_msg = rpc_res.data.get('error', 'Unknown database error') if rpc_res.data else 'Database failure'
                    raise ValueError(f"Transaction failed: {err_msg}")
                    
                amount_spent = tickets * giveaway.get('raffle_cost', 0)
                upsert_data = rpc_res.data['entry']

            elif entry_mode == 'open':
                if existing_entry:
                    raise ValueError("You have already entered this giveaway")
                    
            # Upsert entry manually only if not raffle (raffle does it in RPC)
            if entry_mode != 'raffle':
                upsert_data = {
                    'giveaway_id': giveaway_id,
                    'guild_id': str(guild_id),
                    'user_id': str(user_id),
                    'tickets': tickets + (existing_entry['tickets'] if existing_entry else 0),
                    'amount_spent': amount_spent + (existing_entry['amount_spent'] if existing_entry else 0),
                }
                
                if existing_entry:
                    res = self.data_manager.admin_client.table('giveaway_entries').update({
                        'tickets': upsert_data['tickets'],
                        'amount_spent': upsert_data['amount_spent']
                    }).eq('id', existing_entry['id']).execute()
                else:
                    res = self.data_manager.admin_client.table('giveaway_entries').insert({
                        'giveaway_id': giveaway_id,
                        'guild_id': str(guild_id),
                        'user_id': str(user_id),
                        'tickets': tickets,
                        'amount_spent': amount_spent
                    }).execute()
    
                # Increment denormalized count (raffle does this inside RPC)
                self.data_manager.admin_client.rpc('increment_giveaway_entries', {'g_id': giveaway_id, 't_count': tickets}).execute()
            
            if self.cache_manager:
                self.cache_manager.invalidate(f"giveaway:{giveaway_id}")

            if self.sse_manager:
                self.sse_manager.broadcast_event('giveaway_entry', {
                    'giveaway_id': giveaway_id,
                    'guild_id': str(guild_id),
                    'total_entries': giveaway['total_entries'] + tickets,
                    'user_id': str(user_id)
                }, target_guild=str(guild_id))

            return upsert_data

        except Exception as e:
            logger.error(f"Error entering giveaway: {e}")
            raise e

    def withdraw_entry(self, giveaway_id: str, guild_id: str, user_id: str) -> dict:
        """Withdraws from a non-raffle giveaway."""
        try:
            giveaway = self.get_giveaway(giveaway_id, guild_id)
            if not giveaway:
                raise ValueError("Giveaway not found")
                
            if giveaway['entry_mode'] == 'raffle':
                raise ValueError("Raffle entries are non-refundable")
                
            entry = self.get_user_entry(giveaway_id, user_id)
            if not entry:
                raise ValueError("You have not entered this giveaway")
                
            self.data_manager.admin_client.table('giveaway_entries').delete().eq('id', entry['id']).execute()
            
            # Decrement denormalized count
            self.data_manager.admin_client.rpc('increment_giveaway_entries', {'g_id': giveaway_id, 't_count': -entry['tickets']}).execute()
            
            if self.cache_manager:
                self.cache_manager.invalidate(f"giveaway:{giveaway_id}")

            return {'success': True}

        except Exception as e:
            logger.error(f"Error withdrawing entry: {e}")
            raise e

    async def refresh_giveaway_embed(self, giveaway_id: str):
        """Updates the live message with new entry count and time left."""
        if not self.bot:
            return
            
        try:
            giveaway = self.get_giveaway(giveaway_id, None)
            if not giveaway or giveaway['status'] != 'active' or not giveaway.get('message_id'):
                return
                
            channel = await self._robust_get_channel(int(giveaway['channel_id']))
            if not channel:
                logger.warning(f"Could not find channel {giveaway['channel_id']} for embed refresh")
                return
                
            try:
                message = await channel.fetch_message(int(giveaway['message_id']))
                embed = self._build_live_embed(giveaway)
                await message.edit(embed=embed)
            except discord.NotFound:
                # Message was deleted, mark null so background loop posts it again
                self.data_manager.admin_client.table('giveaways').update({'message_id': None}).eq('id', giveaway_id).execute()
        except Exception as e:
            logger.error(f"Error refreshing embed: {e}")

    async def end_giveaway(self, giveaway_id: str, reroll: bool = False) -> list:
        """Ends the giveaway and draws winners."""
        try:
            giveaway = self.get_giveaway(giveaway_id, None)
            if not giveaway:
                raise ValueError("Giveaway not found")
                
            if not reroll and giveaway['status'] != 'active':
                raise ValueError("Giveaway is not active")
            if reroll and giveaway['status'] != 'ended':
                raise ValueError("Can only reroll an ended giveaway")

            # Fetch entries
            entries = self.data_manager.admin_client.table('giveaway_entries').select('*').eq('giveaway_id', giveaway_id).execute()
            
            pool = []
            unique_users = set()
            
            # Formally reconstruct past winners specifically to guarantee their complete exclusion across all successive rerolls
            past_winners = set(giveaway.get('past_winners', []))
            if reroll:
                past_winners.update(giveaway.get('winner_user_ids', []))
            
            for entry in entries.data:
                u_id = entry['user_id']
                if reroll and u_id in past_winners:
                    continue
                unique_users.add(u_id)
                pool.extend([u_id] * entry['tickets'])
                
            winners = []
            winner_count = min(giveaway['winner_count'], len(unique_users))
            
            while len(winners) < winner_count and pool:
                chosen = random.choice(pool)
                winners.append(chosen)
                # Remove all tickets for this user from the pool to prevent duplicates
                pool = [u for u in pool if u != chosen]
                
            # Update status
            upd = {
                'status': 'ended',
                'ended_at': datetime.now(timezone.utc).isoformat(),
                'winner_user_ids': winners,
                'past_winners': list(past_winners)
            }
            self.data_manager.admin_client.table('giveaways').update(upd).eq('id', giveaway_id).execute()
            giveaway.update(upd)
            
            if self.cache_manager:
                self.cache_manager.invalidate(f"giveaway:{giveaway_id}")

            # Determine if the drawing is late due to bot downtime
            ends_at = datetime.fromisoformat(giveaway['ends_at'].replace('Z', '+00:00'))
            delay_seconds = (datetime.now(timezone.utc) - ends_at).total_seconds()
            
            # Send announcement
            if self.bot:
                await self._post_winner_announcement(giveaway, is_delayed=(delay_seconds > 300))
                
                # Edit live embed to ended state
                if giveaway.get('message_id'):
                    try:
                        channel = self.bot.get_channel(int(giveaway['channel_id']))
                        if channel:
                            msg = await channel.fetch_message(int(giveaway['message_id']))
                            await msg.edit(embed=self._build_ended_embed(giveaway), view=None)
                            
                            # Schedule deletion using config or fallback
                            from config import config
                            delay = getattr(config, 'giveaway_embed_delete_delay', 30)
                            self.bot.loop.create_task(self._delete_embed_after_delay(channel, msg, delay))
                    except Exception as e:
                        logger.warning(f"Failed to edit/schedule delete for ended embed {giveaway_id}: {e}")

            if hasattr(self.data_manager, 'bot') and hasattr(self.data_manager.bot, 'audit_manager') and self.data_manager.bot.audit_manager:
                self.data_manager.bot.audit_manager.log_event(
                    AuditEventType.GIVEAWAY_ENDED,
                    guild_id=int(giveaway['guild_id']),
                    user_id=None,
                    moderator_id=int(giveaway['created_by']),
                    details={'giveaway_id': giveaway_id, 'winners': winners}
                )

            if self.sse_manager:
                self.sse_manager.broadcast_event('giveaway_ended', {
                    'giveaway_id': giveaway_id,
                    'guild_id': giveaway['guild_id'],
                    'winner_user_ids': winners,
                    'prize_name': giveaway['prize_name']
                }, target_guild=giveaway['guild_id'])

            return winners

        except Exception as e:
            logger.error(f"Error ending giveaway {giveaway_id}: {e}")
            raise e

    def cancel_giveaway(self, giveaway_id: str, guild_id: str, cancelled_by: str) -> dict:
        """Cancel a giveaway and refund users if it's a raffle."""
        try:
            giveaway = self.get_giveaway(giveaway_id, guild_id)
            if not giveaway:
                raise ValueError("Giveaway not found")
                
            if giveaway['status'] == 'ended' or giveaway['status'] == 'cancelled':
                raise ValueError("Cannot cancel an ended/cancelled giveaway")

            # Process refunds if raffle
            refund_count = 0
            if giveaway['entry_mode'] == 'raffle':
                entries = self.data_manager.admin_client.table('giveaway_entries').select('*').eq('giveaway_id', giveaway_id).gt('amount_spent', 0).execute()
                for entry in entries.data:
                    if self.transaction_manager:
                        self.transaction_manager.add_transaction(
                            str(guild_id), entry['user_id'], entry['amount_spent'],
                            reason=f"Refund from cancelled giveaway: {giveaway['prize_name']}",
                            transaction_type="giveaway_refund"
                        )
                        refund_count += 1
                        
                        # Note: DMing user would require async, probably better off silently refunding or doing via a task

            self.data_manager.admin_client.table('giveaways').update({
                'status': 'cancelled',
                'ended_at': datetime.now(timezone.utc).isoformat()
            }).eq('id', giveaway_id).execute()
            
            if self.cache_manager:
                self.cache_manager.invalidate(f"giveaway:{giveaway_id}")
                
            if self.bot and giveaway.get('message_id'):
                try:
                    # Use robust deletion helper
                    logger.info(f"Attempting to delete giveaway message {giveaway['message_id']} in channel {giveaway['channel_id']}")
                    self.bot.loop.create_task(self._robust_delete_message(
                        int(giveaway['channel_id']), 
                        int(giveaway['message_id'])
                    ))
                except Exception as e:
                    logger.error(f"Failed to queue giveaway message deletion: {e}")

            if hasattr(self.data_manager, 'bot') and hasattr(self.data_manager.bot, 'audit_manager') and self.data_manager.bot.audit_manager:
                self.data_manager.bot.audit_manager.log_event(
                    AuditEventType.GIVEAWAY_CANCELLED,
                    guild_id=int(guild_id),
                    user_id=None,
                    moderator_id=int(cancelled_by),
                    details={'giveaway_id': giveaway_id, 'refund_count': refund_count}
                )

            if self.sse_manager:
                self.sse_manager.broadcast_event('giveaway_cancelled', {
                    'giveaway_id': giveaway_id,
                    'guild_id': str(guild_id)
                }, target_guild=str(guild_id))

            return {'success': True, 'refund_count': refund_count}

        except Exception as e:
            logger.error(f"Error cancelling giveaway {giveaway_id}: {e}")
            raise e

    async def reroll_giveaway(self, giveaway_id: str, guild_id: str) -> list:
        return await self.end_giveaway(giveaway_id, reroll=True)

    def get_giveaway(self, giveaway_id: str, guild_id: str = None) -> dict:
        """Fetch a specific giveaway."""
        q = self.data_manager.admin_client.table('giveaways').select('*').eq('id', giveaway_id)
        if guild_id:
            q = q.eq('guild_id', str(guild_id))
        res = q.execute()
        return res.data[0] if res.data else None

    def get_giveaways(self, guild_id: str, status: str = None, limit: int = 50, offset: int = 0) -> list:
        """Fetch all giveaways for a guild."""
        q = self.data_manager.admin_client.table('giveaways').select('*').eq('guild_id', str(guild_id)).order('created_at', desc=True)
        if status:
            q = q.eq('status', status)
        res = q.range(offset, offset + limit - 1).execute()
        return res.data

    def get_user_entry(self, giveaway_id: str, user_id: str) -> dict:
        """Fetch a user's entry for a giveaway."""
        res = self.data_manager.admin_client.table('giveaway_entries').select('*').eq('giveaway_id', giveaway_id).eq('user_id', str(user_id)).execute()
        return res.data[0] if res.data else None
        
    def update_giveaway(self, giveaway_id: str, guild_id: str, updates: dict) -> dict:
        """Update allowed fields of a giveaway."""
        allowed_fields = ['ends_at', 'custom_message', 'tag_role_id', 'prize_description', 'prize_image_url', 'winner_count']
        data = {k: v for k, v in updates.items() if k in allowed_fields}
        if not data:
            return self.get_giveaway(giveaway_id, guild_id)
            
        res = self.data_manager.admin_client.table('giveaways').update(data).eq('id', giveaway_id).eq('guild_id', str(guild_id)).execute()
        
        if self.cache_manager:
            self.cache_manager.invalidate(f"giveaway:{giveaway_id}")
            
        if self.sse_manager:
            self.sse_manager.broadcast_event('giveaway_updated', {
                'giveaway_id': giveaway_id,
                'guild_id': str(guild_id),
                'updates': data
            }, target_guild=str(guild_id))
            
        if self.bot and self.bot.loop:
            self.bot.loop.create_task(self.refresh_giveaway_embed(giveaway_id))
            
        return res.data[0] if res.data else None

    def _build_live_embed(self, giveaway: dict) -> discord.Embed:
        embed = discord.Embed(
            title=f"🎉 {giveaway['prize_name']}",
            description=giveaway.get('prize_description', ''),
            color=0x57F287
        )
        if giveaway.get('prize_image_url'):
            embed.set_image(url=giveaway['prize_image_url'])

        # Instructions
        mode = giveaway['entry_mode']
        if mode == 'open':
            instructions = "Click the button below to enter for free"
        elif mode == 'role_restricted':
            roles = " ".join([f"<@&{r}>" for r in giveaway.get('required_role_ids', [])])
            instructions = f"You must have: {roles} to enter"
        elif mode == 'raffle':
            currency_name = "coins"  # Fallback
            try:
                config = self.data_manager.load_guild_data(giveaway['guild_id'], 'config')
                if config and config.get('currency_name'):
                    currency_name = config['currency_name']
            except: pass
            cost = giveaway.get('raffle_cost', 0)
            mx = giveaway.get('raffle_max_tickets_per_user', 10)
            instructions = f"Buy tickets with {currency_name}: {cost} per ticket (max {mx} tickets)"

        embed.add_field(name="How to Enter", value=instructions, inline=False)
        embed.add_field(name="Winners", value=f"{giveaway['winner_count']} winner(s) will be drawn", inline=True)
        embed.add_field(name="Entries", value=f"{giveaway['total_entries']} entries", inline=True)

        ends_at = datetime.fromisoformat(giveaway['ends_at'].replace('Z', '+00:00'))
        timestamp = int(ends_at.timestamp())
            
        embed.add_field(name="Time Left", value=f"<t:{timestamp}:R>", inline=True)
        embed.set_footer(text="Ends")
        embed.timestamp = ends_at
        
        return embed

    def _build_ended_embed(self, giveaway: dict) -> discord.Embed:
        embed = discord.Embed(
            title=f"🎊 GIVEAWAY ENDED — {giveaway['prize_name']}",
            color=0x95A5A6
        )
        
        winners = giveaway.get('winner_user_ids', [])
        if winners:
            winners_str = ", ".join([f"<@{w}>" for w in winners])
        else:
            winners_str = "No valid entries"
            
        embed.add_field(name="Winner(s)", value=winners_str, inline=False)
        embed.add_field(name="Total Entries", value=str(giveaway['total_entries']), inline=False)
        
        ended_at = giveaway.get('ended_at')
        if ended_at:
            embed.timestamp = datetime.fromisoformat(ended_at.replace('Z', '+00:00'))
            embed.set_footer(text="Ended")
            
        return embed

    async def _post_winner_announcement(self, giveaway: dict, is_delayed: bool = False):
        try:
            channel = await self._robust_get_channel(int(giveaway['channel_id']))
            if not channel:
                logger.warning(f"Could not find channel {giveaway['channel_id']} for winner announcement")
                return
                
            winners = giveaway.get('winner_user_ids', [])
            if not winners:
                msg = f"Giveaway for **{giveaway['prize_name']}** has ended. Unfortunately, there were no entries — no winner drawn."
                if is_delayed:
                    msg = "⚠️ *Note: This drawing was delayed due to system maintenance.*\n" + msg
                await channel.send(msg)
                return
                
            winners_str = ", ".join([f"<@{w}>" for w in winners])
            from cogs.giveaways import GiveawayReviewView
            view = GiveawayReviewView(giveaway['id'])
            
            content = f"🎉 Congratulations {winners_str}! You won the **{giveaway['prize_name']}**!"
            if is_delayed:
                content = "⚠️ *Note: This giveaway drawing was delayed due to system maintenance.*\n" + content
                
            await channel.send(content, view=view)
        except discord.Forbidden:
            logger.warning(f"Forbidden to post winner announcement in {giveaway['channel_id']}")
        except Exception as e:
            logger.error(f"Error posting winner announcement: {e}")

    async def _delete_embed_after_delay(self, channel, message, delay_seconds: int):
        try:
            await asyncio.sleep(delay_seconds)
            await message.delete()
        except discord.NotFound:
            pass
        except Exception as e:
            logger.error(f"Failed to delete ended embed: {e}")
            
    async def _delete_cancelled_message(self, channel, message_id):
        try:
            msg = await channel.fetch_message(int(message_id))
            await msg.delete()
            logger.info(f"Successfully deleted cancelled giveaway message {message_id}")
        except discord.NotFound:
            logger.warning(f"Giveaway message {message_id} already deleted")
        except Exception as e:
            logger.error(f"Failed to delete giveaway message {message_id}: {e}")

    async def _robust_get_channel(self, channel_id: int):
        """Get channel from cache or fetch if not found"""
        if not self.bot:
            return None
        
        channel = self.bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception as e:
                logger.error(f"Failed to fetch channel {channel_id}: {e}")
                return None
        return channel

    async def _robust_delete_message(self, channel_id: int, message_id: int):
        """Robustly delete a message by fetching channel first if needed"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.info(f"Channel {channel_id} not in cache, fetching...")
                channel = await self.bot.fetch_channel(channel_id)
            
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    await message.delete()
                    logger.info(f"Successfully deleted message {message_id} in channel {channel_id}")
                except discord.NotFound:
                    logger.warning(f"Message {message_id} not found in channel {channel_id}")
                except discord.Forbidden:
                    logger.error(f"No permission to delete message {message_id} in channel {channel_id}")
            else:
                logger.error(f"Could not find/fetch channel {channel_id} to delete message")
        except Exception as e:
            logger.error(f"Error in _robust_delete_message: {e}")
