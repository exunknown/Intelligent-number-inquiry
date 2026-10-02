"""Pure resolution of governed metric equivalence and attachment relations."""

from collections.abc import Mapping
from dataclasses import dataclass

from app.entities.auth import PermissionSnapshot
from app.entities.cube_member import CubeMember
from app.entities.semantic_model import (
    SemanticMember,
    SemanticMetricAttachment,
    SemanticMetricEquivalenceGroup,
    SemanticMetricEquivalenceMember,
    SemanticModelSnapshot,
)


@dataclass(frozen=True)
class ResolvedMetricAttachment:
    """A permitted directly attached metric plus its display metadata."""

    member: CubeMember
    relation_type: str
    note: str
    display_order: int


@dataclass(frozen=True)
class SemanticMetricRelationResolution:
    """The canonical query measure and optional one-hop display attachments."""

    primary: CubeMember | None
    attachments: tuple[ResolvedMetricAttachment, ...] = ()
    compatibility_notes: tuple[str, ...] = ()

    @property
    def members(self) -> tuple[CubeMember, ...]:
        """Return primary and attached members without duplicate query columns."""

        if self.primary is None:
            return ()
        seen = {self.primary.name}
        members = [self.primary]
        for attachment in self.attachments:
            if attachment.member.name not in seen:
                seen.add(attachment.member.name)
                members.append(attachment.member)
        return tuple(members)

    @property
    def relation_notes(self) -> tuple[str, ...]:
        """Compatibility alias for consumers that render relation metadata."""

        return self.compatibility_notes


class SemanticMetricRelationService:
    """Resolve semantic metric relations without repository or client access."""

    def resolve(
        self,
        requested_metric: str | CubeMember,
        snapshot: SemanticModelSnapshot,
        permissions: PermissionSnapshot,
        member_catalog: Mapping[str, CubeMember],
        *,
        expand_attachments: bool = True,
    ) -> SemanticMetricRelationResolution:
        """Resolve one requested measure against one release and permission snapshot.

        Relation records are release-local through ``snapshot``. Expansion examines
        only attachments whose primary is the resolved canonical member, so cycles
        and longer chains cannot cause recursion or additional query columns.
        """

        semantic_members = {member.member_id: member for member in snapshot.members}
        requested_name = (
            requested_metric.name
            if isinstance(requested_metric, CubeMember)
            else requested_metric
        )
        requested_cube_member = member_catalog.get(requested_name)
        if requested_cube_member is None:
            return SemanticMetricRelationResolution(primary=None)

        requested_semantic = self._semantic_member_for_name(
            snapshot.members, requested_cube_member.name
        )
        if requested_semantic is None or requested_semantic.member_type != "measure":
            return SemanticMetricRelationResolution(primary=None)

        group, relation_member = self._equivalence_for(
            snapshot.metric_equivalence_groups, requested_semantic.member_id
        )
        canonical_id = (
            group.canonical_member_id
            if group is not None
            else requested_semantic.member_id
        )
        canonical_semantic = semantic_members.get(canonical_id)
        canonical = self._permitted_cube_member(
            canonical_semantic, member_catalog, permissions
        )
        if canonical is None:
            return SemanticMetricRelationResolution(primary=None)

        compatibility_notes = ()
        if relation_member is not None and relation_member.match_type == "compatible":
            if relation_member.note:
                compatibility_notes = (relation_member.note,)

        if not expand_attachments:
            return SemanticMetricRelationResolution(
                primary=canonical, compatibility_notes=compatibility_notes
            )

        attachments = self._expand_direct_attachments(
            snapshot.metric_attachments,
            canonical_id,
            frozenset(relation.member_id for relation in group.members)
            if group is not None
            else frozenset({canonical_id}),
            semantic_members,
            member_catalog,
            permissions,
            canonical.name,
        )
        return SemanticMetricRelationResolution(
            primary=canonical,
            attachments=attachments,
            compatibility_notes=compatibility_notes,
        )

    @staticmethod
    def _semantic_member_for_name(
        members: tuple[SemanticMember, ...], name: str
    ) -> SemanticMember | None:
        for member in members:
            if member.qualified_name == name:
                return member
        return None

    @staticmethod
    def _equivalence_for(
        groups: tuple[SemanticMetricEquivalenceGroup, ...], member_id: str
    ) -> tuple[
        SemanticMetricEquivalenceGroup | None,
        SemanticMetricEquivalenceMember | None,
    ]:
        for group in groups:
            for relation_member in group.members:
                if relation_member.member_id == member_id:
                    return group, relation_member
        return None, None

    @staticmethod
    def _permitted_cube_member(
        semantic_member: SemanticMember | None,
        member_catalog: Mapping[str, CubeMember],
        permissions: PermissionSnapshot,
    ) -> CubeMember | None:
        if semantic_member is None or semantic_member.member_type != "measure":
            return None
        member = member_catalog.get(semantic_member.qualified_name)
        if member is None or member.member_type != "measure":
            return None
        if member.name not in permissions.allowed_metrics:
            return None
        return member

    @classmethod
    def _expand_direct_attachments(
        cls,
        attachments: tuple[SemanticMetricAttachment, ...],
        primary_id: str,
        equivalent_member_ids: frozenset[str],
        semantic_members: Mapping[str, SemanticMember],
        member_catalog: Mapping[str, CubeMember],
        permissions: PermissionSnapshot,
        primary_name: str,
    ) -> tuple[ResolvedMetricAttachment, ...]:
        resolved: list[ResolvedMetricAttachment] = []
        seen_names = {primary_name}
        indexed = enumerate(attachments)
        for _, attachment in sorted(
            indexed, key=lambda item: (item[1].display_order, item[0])
        ):
            if (
                not attachment.default_visible
                or attachment.primary_member_id != primary_id
            ):
                continue
            if attachment.attached_member_id in equivalent_member_ids:
                continue
            semantic_member = semantic_members.get(attachment.attached_member_id)
            member = cls._permitted_cube_member(
                semantic_member, member_catalog, permissions
            )
            if member is None or member.name in seen_names:
                continue
            seen_names.add(member.name)
            resolved.append(
                ResolvedMetricAttachment(
                    member=member,
                    relation_type=attachment.relation_type,
                    note=attachment.note,
                    display_order=attachment.display_order,
                )
            )
        return tuple(resolved)


def resolve_semantic_metric_relations(
    requested_metric: str | CubeMember,
    snapshot: SemanticModelSnapshot,
    permissions: PermissionSnapshot,
    member_catalog: Mapping[str, CubeMember],
    *,
    expand_attachments: bool = True,
) -> SemanticMetricRelationResolution:
    """Functional entry point for callers that do not need a service instance."""

    return SemanticMetricRelationService().resolve(
        requested_metric,
        snapshot,
        permissions,
        member_catalog,
        expand_attachments=expand_attachments,
    )
