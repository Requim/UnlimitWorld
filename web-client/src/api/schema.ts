export interface paths {
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Health
         * @description 返回进程健康状态；无入参、无存储副作用。
         */
        get: operations["health_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v2/catalog": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Catalog
         * @description 返回完整卡牌、法宝、敌人与流派目录；无存储副作用。
         */
        get: operations["catalog_api_v2_catalog_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v2/runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Run
         * @description 创建匿名局面；可用既有 Bearer 归属同档案，错误凭证返回 401。
         */
        post: operations["create_run_api_v2_runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v2/runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Run
         * @description 读取 Bearer 所属权威局面；无写副作用，缺失或错误凭证返回 401。
         */
        get: operations["get_run_api_v2_runs__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v2/runs/{run_id}/actions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Perform Action
         * @description 原子提交类型化动作；成功推进 revision，非法动作不落盘。
         */
        post: operations["perform_action_api_v2_runs__run_id__actions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * ActionRequest
         * @description 扁平动作 JSON 的判别联合根模型。
         */
        ActionRequest: components["schemas"]["ChooseNodeAction"] | components["schemas"]["PlayCardAction"] | components["schemas"]["EndTurnAction"] | components["schemas"]["TauntAction"] | components["schemas"]["ChooseRewardAction"] | components["schemas"]["SkipRewardAction"] | components["schemas"]["ChooseEventAction"] | components["schemas"]["BuyAction"] | components["schemas"]["RemoveCardAction"] | components["schemas"]["RestAction"] | components["schemas"]["UpgradeCardAction"] | components["schemas"]["LeaveShopAction"];
        /** ArchetypeDefinition */
        ArchetypeDefinition: {
            /**
             * Id
             * @enum {string}
             */
            id: "sword" | "fire" | "talisman";
            /** Name */
            name: string;
            /** Description */
            description: string;
            /** Starter Card Id */
            starter_card_id: string;
        };
        /** BuyAction */
        BuyAction: {
            /** Action Id */
            action_id: string;
            /** Expected Revision */
            expected_revision: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "buy";
            /** Item Id */
            item_id: string;
        };
        /** CardDefinition */
        CardDefinition: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /**
             * Archetype
             * @enum {string}
             */
            archetype: "common" | "sword" | "fire" | "talisman";
            /** Cost */
            cost: number;
            /** Upgraded Cost */
            upgraded_cost: number;
            /**
             * Target
             * @enum {string}
             */
            target: "enemy" | "self" | "none";
            /** Description */
            description: string;
            /** Upgrade Text */
            upgrade_text: string;
            /**
             * Exhaust
             * @default false
             */
            exhaust: boolean;
        };
        /** CardInstance */
        CardInstance: {
            /** Uid */
            uid: string;
            /** Card Id */
            card_id: string;
            /**
             * Upgraded
             * @default false
             */
            upgraded: boolean;
        };
        /** CatalogResponse */
        CatalogResponse: {
            /** Cards */
            cards: components["schemas"]["CardDefinition"][];
            /** Relics */
            relics: components["schemas"]["RelicDefinition"][];
            /** Enemies */
            enemies: components["schemas"]["EnemyDefinition"][];
            /** Archetypes */
            archetypes: components["schemas"]["ArchetypeDefinition"][];
        };
        /** ChooseEventAction */
        ChooseEventAction: {
            /** Action Id */
            action_id: string;
            /** Expected Revision */
            expected_revision: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "choose_event";
            /** Choice Id */
            choice_id: string;
        };
        /** ChooseNodeAction */
        ChooseNodeAction: {
            /** Action Id */
            action_id: string;
            /** Expected Revision */
            expected_revision: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "choose_node";
            /** Node Id */
            node_id: string;
        };
        /** ChooseRewardAction */
        ChooseRewardAction: {
            /** Action Id */
            action_id: string;
            /** Expected Revision */
            expected_revision: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "choose_reward";
            /** Option Index */
            option_index: number;
        };
        /** CombatPresentationSnapshot */
        CombatPresentationSnapshot: {
            player: components["schemas"]["PlayerPresentationState"];
            enemy: components["schemas"]["EnemyPresentationState"];
            /** Turn */
            turn?: number | null;
            /** Energy */
            energy?: number | null;
        };
        /** CombatView */
        CombatView: {
            /** Turn */
            turn: number;
            /** Energy */
            energy: number;
            /** Max Energy */
            max_energy: number;
            /** Hand */
            hand: components["schemas"]["CardInstance"][];
            /** Draw Count */
            draw_count: number;
            /** Discard Count */
            discard_count: number;
            /** Exhaust Count */
            exhaust_count: number;
            enemy: components["schemas"]["EnemyState"];
            /** Taunt Used */
            taunt_used: boolean;
            taunt_preview: components["schemas"]["TauntPreview"];
            /** Sword Intent */
            sword_intent: number;
            /** Lightning Redirect */
            lightning_redirect: boolean;
            /** Thunder Count */
            thunder_count: number;
            /**
             * Thunder Damage
             * @default 8
             */
            thunder_damage: number;
        };
        /** CreateRunRequest */
        CreateRunRequest: {
            /**
             * Archetype
             * @enum {string}
             */
            archetype: "sword" | "fire" | "talisman";
            /**
             * Mode
             * @default classic
             * @enum {string}
             */
            mode: "classic" | "myth_bifang";
        };
        /** CreateRunResponse */
        CreateRunResponse: {
            run: components["schemas"]["RunView"];
            /** Events */
            events: components["schemas"]["GameEvent"][];
            /** Access Token */
            access_token: string;
        };
        /** EndTurnAction */
        EndTurnAction: {
            /** Action Id */
            action_id: string;
            /** Expected Revision */
            expected_revision: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "end_turn";
        };
        /** EnemyDefinition */
        EnemyDefinition: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /**
             * Rank
             * @enum {string}
             */
            rank: "normal" | "elite" | "boss";
            /** Max Hp */
            max_hp: number;
            /** Intent Pattern */
            intent_pattern: [
                string,
                number
            ][];
            /** Description */
            description: string;
        };
        /** EnemyIntent */
        EnemyIntent: {
            /**
             * Kind
             * @enum {string}
             */
            kind: "attack" | "defend" | "burn" | "multi";
            /**
             * Value
             * @description 已计入虚弱和挑衅的每段最终伤害，防御时为护盾值
             */
            value: number;
            /**
             * Hits
             * @description 该意图的攻击段数
             * @default 1
             */
            hits: number;
            /**
             * Wrath Change
             * @description 意图命中且双方存活时造成的天谴变化
             * @default 0
             */
            wrath_change: number;
            /** Text */
            text: string;
        };
        /** EnemyPresentationState */
        EnemyPresentationState: {
            /** Hp */
            hp: number;
            /** Block */
            block: number;
            /** Burn */
            burn: number;
            /** Weak */
            weak: number;
        };
        /** EnemyState */
        EnemyState: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Hp */
            hp: number;
            /** Max Hp */
            max_hp: number;
            /**
             * Block
             * @default 0
             */
            block: number;
            /**
             * Burn
             * @default 0
             */
            burn: number;
            /**
             * Weak
             * @default 0
             */
            weak: number;
            /**
             * Intent Index
             * @default 0
             */
            intent_index: number;
            intent: components["schemas"]["EnemyIntent"];
        };
        /** EventChoice */
        EventChoice: {
            /** Id */
            id: string;
            /** Label */
            label: string;
            /** Description */
            description: string;
        };
        /** GameEvent */
        GameEvent: {
            /** Kind */
            kind: string;
            /** Text */
            text: string;
            /** Amount */
            amount?: number | null;
            /** Target */
            target?: string | null;
            /** Source */
            source?: ("player" | "enemy" | "heaven" | "system") | null;
            /** Card Id */
            card_id?: string | null;
            /** Visual */
            visual?: ("sword" | "fire" | "shield" | "thunder" | "hit" | "defeat" | "idle") | null;
            /** Absorbed */
            absorbed?: number | null;
            state_after?: components["schemas"]["CombatPresentationSnapshot"] | null;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** HistoryEntry */
        HistoryEntry: {
            /** Revision */
            revision: number;
            /** Kind */
            kind: string;
            /** Text */
            text: string;
        };
        /** LeaveShopAction */
        LeaveShopAction: {
            /** Action Id */
            action_id: string;
            /** Expected Revision */
            expected_revision: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "leave_shop";
        };
        /** MapNode */
        MapNode: {
            /** Id */
            id: string;
            /** Layer */
            layer: number;
            /** Lane */
            lane: number;
            /**
             * Kind
             * @enum {string}
             */
            kind: "combat" | "elite" | "event" | "shop" | "rest" | "boss";
            /** Links From */
            links_from?: string[];
            /**
             * Available
             * @default false
             */
            available: boolean;
            /**
             * Completed
             * @default false
             */
            completed: boolean;
        };
        /** PlayCardAction */
        PlayCardAction: {
            /** Action Id */
            action_id: string;
            /** Expected Revision */
            expected_revision: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "play_card";
            /** Card Uid */
            card_uid: string;
            /** Target Id */
            target_id?: string | null;
        };
        /** PlayerPresentationState */
        PlayerPresentationState: {
            /** Hp */
            hp: number;
            /** Block */
            block: number;
            /** Wrath */
            wrath: number;
            /** Reflect */
            reflect: number;
        };
        /** PlayerState */
        PlayerState: {
            /**
             * Hp
             * @default 60
             */
            hp: number;
            /**
             * Max Hp
             * @default 60
             */
            max_hp: number;
            /**
             * Block
             * @default 0
             */
            block: number;
            /**
             * Wrath
             * @default 0
             */
            wrath: number;
            /**
             * Stones
             * @default 60
             */
            stones: number;
            /**
             * Reflect
             * @default 0
             */
            reflect: number;
        };
        /** RelicDefinition */
        RelicDefinition: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Description */
            description: string;
        };
        /** RemoveCardAction */
        RemoveCardAction: {
            /** Action Id */
            action_id: string;
            /** Expected Revision */
            expected_revision: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "remove_card";
            /** Card Uid */
            card_uid: string;
        };
        /** RestAction */
        RestAction: {
            /** Action Id */
            action_id: string;
            /** Expected Revision */
            expected_revision: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "rest";
            /**
             * Mode
             * @enum {string}
             */
            mode: "heal" | "upgrade";
        };
        /** RewardCard */
        RewardCard: {
            /** Card Id */
            card_id: string;
            /**
             * Upgraded
             * @default false
             */
            upgraded: boolean;
        };
        /** RewardState */
        RewardState: {
            /** Cards */
            cards: components["schemas"]["RewardCard"][];
            /** Stones */
            stones: number;
            /**
             * Source
             * @enum {string}
             */
            source: "normal" | "elite";
        };
        /** RunMap */
        RunMap: {
            /** Nodes */
            nodes: components["schemas"]["MapNode"][];
            /** Current Node Id */
            current_node_id?: string | null;
        };
        /** RunResponse */
        RunResponse: {
            run: components["schemas"]["RunView"];
            /** Events */
            events: components["schemas"]["GameEvent"][];
        };
        /** RunView */
        RunView: {
            /** Run Id */
            run_id: string;
            /** Revision */
            revision: number;
            /**
             * Archetype
             * @enum {string}
             */
            archetype: "sword" | "fire" | "talisman";
            /**
             * Mode
             * @default classic
             * @enum {string}
             */
            mode: "classic" | "myth_bifang";
            /**
             * Phase
             * @enum {string}
             */
            phase: "map" | "combat" | "battle_won" | "reward" | "event" | "shop" | "rest" | "rest_upgrade" | "completed" | "game_over";
            /** Layer */
            layer: number;
            player: components["schemas"]["PlayerState"];
            /** Deck */
            deck: components["schemas"]["CardInstance"][];
            /** Relics */
            relics: string[];
            map: components["schemas"]["RunMap"];
            combat: components["schemas"]["CombatView"] | null;
            reward: components["schemas"]["RewardState"] | null;
            /** Choices */
            choices: components["schemas"]["EventChoice"][];
            shop: components["schemas"]["ShopState"] | null;
            /** History */
            history: components["schemas"]["HistoryEntry"][];
            /** Epitaph */
            epitaph: string | null;
            story?: components["schemas"]["StoryView"] | null;
        };
        /** ShopItem */
        ShopItem: {
            /** Id */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "card" | "relic";
            /** Ref Id */
            ref_id: string;
            /** Price */
            price: number;
            /**
             * Purchased
             * @default false
             */
            purchased: boolean;
        };
        /** ShopState */
        ShopState: {
            /** Items */
            items: components["schemas"]["ShopItem"][];
            /**
             * Removal Price
             * @default 45
             */
            removal_price: number;
            /**
             * Removal Used
             * @default false
             */
            removal_used: boolean;
        };
        /** SkipRewardAction */
        SkipRewardAction: {
            /** Action Id */
            action_id: string;
            /** Expected Revision */
            expected_revision: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "skip_reward";
        };
        /** StoryChoice */
        StoryChoice: {
            /** Id */
            id: string;
            /** Label */
            label: string;
            /** Consequence */
            consequence: string;
        };
        /** StoryView */
        StoryView: {
            /** Id */
            id: string;
            /** Version */
            version: string;
            /** Title */
            title: string;
            /** Body */
            body: string;
            /** Choices */
            choices: components["schemas"]["StoryChoice"][];
            /** Selected Choice */
            selected_choice?: string | null;
        };
        /** TauntAction */
        TauntAction: {
            /** Action Id */
            action_id: string;
            /** Expected Revision */
            expected_revision: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "taunt";
        };
        /** TauntPreview */
        TauntPreview: {
            /** Available */
            available: boolean;
            /**
             * Energy Gain
             * @description 提交挑衅后立即获得的灵力
             */
            energy_gain: number;
            /**
             * Wrath Change
             * @description 计入法宝后的实际天谴变化
             */
            wrath_change: number;
            /**
             * Next Attack Bonus
             * @description 敌人下一次真实攻击的每段伤害加成
             */
            next_attack_bonus: number;
            /**
             * Text
             * @description 前端可直接展示的完整效果说明
             */
            text: string;
        };
        /** UpgradeCardAction */
        UpgradeCardAction: {
            /** Action Id */
            action_id: string;
            /** Expected Revision */
            expected_revision: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "upgrade_card";
            /** Card Uid */
            card_uid: string;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    health_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
        };
    };
    catalog_api_v2_catalog_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogResponse"];
                };
            };
        };
    };
    create_run_api_v2_runs_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateRunRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreateRunResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_run_api_v2_runs__run_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    perform_action_api_v2_runs__run_id__actions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ActionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
